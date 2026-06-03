import asyncio
import logging
import os
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

if not BOT_TOKEN:
    raise RuntimeError(
        "Не найден BOT_TOKEN.\n"
        "Убедитесь, что файл .env лежит рядом с bot.py и содержит строку:\n"
        "BOT_TOKEN=ваш_токен"
    )

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
        except RuntimeError as e:
            log.warning("Ошибка скачивания user=%s err=%s", message.from_user and message.from_user.id, e)
            await status_msg.edit_text(
                "⚠️ Не удалось скачать видео.\n"
                "Проверьте ссылку или попробуйте позже.\n"
                "Если ошибка повторяется — /support"
            )
        except Exception as e:
            log.exception("Непредвиденная ошибка: %s", e)
            await status_msg.edit_text(
                "⚠️ Произошла непредвиденная ошибка.\n"
                "Попробуйте позже или обратитесь в /support."
            )


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    log.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
