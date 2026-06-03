import asyncio
import logging
import os
import random
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
ADMIN_ID = int((os.getenv("ADMIN_ID") or "0").strip())
ADMIN_USERNAME = (os.getenv("ADMIN_USERNAME") or "admin").strip().lstrip("@")

STICKER_START = os.getenv("STICKER_START", "")
STICKER_ERROR = os.getenv("STICKER_ERROR", "")

SUCCESS_STICKERS = [
    "CAACAgIAAxkBAAMpaiA0I4VmRNO3jtrKRd5RXalG3R8AAkcgAAKTHqlKhXiyWh4qOUE7BA",
    "CAACAgIAAxkBAAMraiA0LJqzx2WIDFKBl-ZaErn4b-QAAo0iAAICv8BKlsBosqOf4RQ7BA",
    "CAACAgIAAxkBAAMtaiA0NZVwmsTtCZadDJToBoOPvIUAAj5EAAKDCDBIrpOCCGu5vDE7BA",
    "CAACAgIAAxkBAAMvaiA0QasBnxoxRnP7hpBL0t3NrXUAAhsiAAJFTElJl7fGOcgLHBY7BA",
    "CAACAgIAAxkBAAMxaiA0SHZCn9oY1XWAxs2SUV7CM5MAAkxoAAJHQbBKnZ33g16Pmng7BA",
    "CAACAgIAAxkBAAMzaiA0TnPtD1AYKwAB3I9Ns87rISn6AAIMIQAC8qTJSHC5SxHhstNJOwQ",
    "CAACAgIAAxkBAAM1aiA0UxyiQtoc4XDkq6Q_CpKtZeAAAh4_AAJCHDhIEq98-78AASVPOwQ",
    "CAACAgIAAxkBAAM3aiA0WDGehyBWpmMJsa4ukAiYULgAAmpMAAIPPTlI0NTR7MKZg1M7BA",
    "CAACAgIAAxkBAAM5aiA0ZQ5BGEa4M_Yf3bw6clowKGwAArM3AALXWbFLCc0-Gqy6zuQ7BA",
    "CAACAgIAAxkBAAM7aiA0azrYhjY14mV_jCDSub8XRhYAApwaAAJtyuFJomvHo-yEyRU7BA",
]

if not BOT_TOKEN:
    available = [k for k in os.environ if not k.startswith("_")]
    log.error("BOT_TOKEN не найден. Доступные переменные: %s", available)
    raise RuntimeError("Не найден BOT_TOKEN в переменных окружения.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

router = Router()

TIKTOK_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "m.tiktok.com",
}


async def send_sticker_if_set(message: Message, file_id: str) -> None:
    if file_id:
        try:
            await message.answer_sticker(file_id)
        except Exception as e:
            log.warning("Не удалось отправить стикер: %s", e)


def extract_tiktok_url(text: str) -> Optional[str]:
    text = text.strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = parsed.netloc.lower()
    if host not in TIKTOK_HOSTS and not host.endswith(".tiktok.com"):
        return None
    return text


def _yt_dlp_bin() -> str:
    venv_bin = BASE_DIR / ".venv" / "bin" / "yt-dlp"
    if venv_bin.exists():
        return str(venv_bin)
    return "yt-dlp"


async def download_video(url: str, output_dir: Path) -> Path:
    output_template = str(output_dir / "%(id)s.%(ext)s")
    cmd = [
        _yt_dlp_bin(),
        "--no-playlist",
        "--format", "mp4/best",
        "--merge-output-format", "mp4",
        "--no-warnings",
        "-o", output_template,
        url,
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        err = (stderr or stdout).decode("utf-8", errors="ignore").strip()
        raise RuntimeError(err or "yt-dlp завершился с ошибкой")

    video_files = sorted(
        [f for f in output_dir.glob("*") if f.is_file() and f.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not video_files:
        raise RuntimeError("Файл видео не найден после скачивания")
    return video_files[0]


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await send_sticker_if_set(message, STICKER_START)
    await message.answer(
        "👋 Привет! Я помогу скачать видео из TikTok без водяных знаков.\n\n"
        "Просто отправьте ссылку на видео — и я пришлю файл.\n\n"
        "📌 /help — как пользоваться\n"
        "🆘 /support — написать администратору"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Как пользоваться: просто пришлите ссылку на видео из TikTok в этот чат, "
        "и бот отправит вам видео без водяных знаков."
    )


@router.message(Command("support"))
async def cmd_support(message: Message) -> None:
    await message.answer(
        f"Если у вас возникли проблемы, напишите администратору: @{ADMIN_USERNAME}"
    )



@router.message(F.text)
async def handle_text(message: Message) -> None:
    text = message.text or ""
    url = extract_tiktok_url(text)

    if not url:
        await message.answer(
            "❌ Это не похоже на ссылку TikTok.\n"
            "Пожалуйста, отправьте корректную ссылку.\n"
            "Если нужна помощь — /support"
        )
        return

    status_msg = await message.answer("⏳ Видео скачивается...")

    with tempfile.TemporaryDirectory(prefix="tiktok_bot_") as tmp:
        try:
            video_path = await download_video(url, Path(tmp))
            await message.answer_video(FSInputFile(video_path))
            await status_msg.edit_text("✅ Готово! Видео отправлено.")
            await send_sticker_if_set(message, random.choice(SUCCESS_STICKERS))
        except RuntimeError as e:
            log.warning("Ошибка скачивания user=%s err=%s", message.from_user and message.from_user.id, e)
            await status_msg.edit_text(
                "⚠️ Не удалось скачать видео.\n"
                "Проверьте ссылку или попробуйте позже.\n"
                "Если ошибка повторяется — /support"
            )
            await send_sticker_if_set(message, STICKER_ERROR)
        except Exception as e:
            log.exception("Непредвиденная ошибка: %s", e)
            await status_msg.edit_text(
                "⚠️ Произошла непредвиденная ошибка.\n"
                "Попробуйте позже или обратитесь в /support."
            )
            await send_sticker_if_set(message, STICKER_ERROR)


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    log.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
