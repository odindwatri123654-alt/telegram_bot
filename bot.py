import asyncio
import logging
import sys
from typing import Optional

from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from people import PEOPLE
from flask import Flask
from threading import Thread
import time

# Создаем Flask-сервер
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive! ✅"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()

# Запускаем веб-сервер ДО запуска бота
keep_alive()
print("✅ Веб-сервер запущен для UptimeRobot")

TOKEN = "8388660314:AAEaZsAIlheJrEQxzSm36zkz4AIo5IDj8tY"


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

dp = Dispatcher()
bot: Optional[Bot] = None


class LoggingMiddleware:
    async def __call__(self, handler, event, data):
        handler_func = data.get('handler', {}).callback
        handler_name = handler_func.__name__ if handler_func else 'unknown'
        logger.debug(f"🟡 Начало обработки события: {handler_name}")
        try:
            result = await handler(event, data)
            logger.debug(f"Успешная обработка: {handler_name}")
            return result
        except Exception as e:
            logger.error(f"Ошибка в обработчике {handler_name}: {e}", exc_info=True)
            raise


logging_middleware = LoggingMiddleware()
for observer in dp.observers.values():
    if observer.event_name != "error":
        observer.middleware(logging_middleware)


def build_back_keyboard() -> InlineKeyboardMarkup:
    logger.debug("Создание клавиатуры 'Назад'")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back")]
    ])


def build_main_keyboard() -> InlineKeyboardMarkup:
    logger.debug("Создание главной клавиатуры")
    kb_builder = InlineKeyboardBuilder()

    logger.debug(f"📋 Доступные ключи в PEOPLE: {list(PEOPLE.keys())}")

    for key in PEOPLE.keys():
        person = PEOPLE[key]
        logger.debug(f"Добавление кнопки: ключ={key}, имя={person.get('name')}")
        kb_builder.button(text=person["name"], callback_data=f"person:{key}")

    kb_builder.adjust(1)
    keyboard = kb_builder.as_markup()
    logger.debug(f"Главная клавиатура создана, кнопок: {len(PEOPLE)}")
    return keyboard

async def send_person_card(chat_id: int, person: dict):
    logger.info(f"Начало отправки карточки: chat_id={chat_id}, person={person.get('name')}")

    if not person:
        logger.error("Передан пустой объект person")
        return

    caption = f"<b>{html.quote(person.get('name', ''))}</b>\n\n{html.quote(person.get('bio', ''))}"
    photo = person.get("photo_url", "")

    logger.debug(f"Подпись: {caption[:100]}...")
    logger.debug(f"Фото: {photo}")

    global bot
    if bot is None:
        logger.error("Bot не инициализирован")
        return

    try:
        logger.info(f"Попытка отправить фото: {photo}")

        if isinstance(photo, str) and (photo.startswith("http://") or photo.startswith("https://")):
            # Отправляем фото по URL
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                reply_markup=build_back_keyboard(),
                parse_mode='HTML'
            )
            logger.info("Фото успешно отправлено по URL")
        else:
            # Fallback: отправляем только текст
            logger.warning("URL фото невалиден, отправляем текстовое сообщение")
            await bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=build_back_keyboard(),
                parse_mode='HTML'
            )
            logger.info("Текстовая карточка успешно отправлена")

    except Exception as e:
        logger.error(f"Критическая ошибка при отправке карточки: {e}", exc_info=True)
        # Финальный fallback
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f"Ошибка загрузки карточки: {html.escape(person.get('name', ''))}",
                reply_markup=build_back_keyboard()
            )
            logger.info("Отправлен fallback-текст")
        except Exception as final_error:
            logger.critical(f"Даже fallback не сработал: {final_error}")


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    logger.info(f"🚀 Команда /start от пользователя {message.from_user.id}")
    try:
        kb = build_main_keyboard()
        await message.answer("НАШИ ГЕРОИ", reply_markup=kb)
        logger.info("Главное меню отправлено")
    except Exception as e:
        logger.error(f"Ошибка в cmd_start: {e}", exc_info=True)


@dp.callback_query(F.data.startswith("person:"))
async def person_callback(callback: CallbackQuery) -> None:
    logger.info(f"Обработка callback: {callback.data}")
    await callback.answer()

    try:
        person_id = callback.data.split(":")[1]
        logger.debug(f"Извлечен person_id: {person_id}")

        person = PEOPLE.get(person_id)
        logger.debug(f"Найден person: {person}")

        if not person:
            logger.warning(f"Человек не найден по ключу: {person_id}")
            await callback.message.answer("Человек не найден")
            return

        logger.info(f"Обработка персонажа: {person.get('name')}")

        try:
            await callback.message.delete()
            logger.info("Сообщение с кнопками удалено")
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")

        # Отправляем карточку
        logger.info(f"Начало отправки карточки для {person.get('name')}")
        await send_person_card(callback.message.chat.id, person)
        logger.info(f"Карточка для {person.get('name')} обработана")

    except Exception as e:
        logger.error(f"Критическая ошибка в person_callback: {e}", exc_info=True)


@dp.callback_query(F.data == "back")
async def back_callback(callback: CallbackQuery) -> None:
    logger.info("Обработка кнопки 'Назад'")
    await callback.answer()

    try:
        # Удаляем текущее сообщение с карточкой
        await callback.message.delete()
        logger.info("Сообщение с карточкой удалено")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение с карточкой: {e}")

    try:
        kb = build_main_keyboard()
        await callback.message.answer("НАШИ ГЕРОИ", reply_markup=kb)
        logger.info("Главное меню отправлено после возврата")
    except Exception as e:
        logger.error(f"Ошибка при отправке главного меню: {e}")

async def main() -> None:
    global bot
    logger.info("Инициализация бота...")
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    try:
        logger.info("Запуск бота...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
    finally:
        if bot is not None:
            await bot.session.close()
            logger.info("Сессия бота закрыта")


if __name__ == "__main__":
    logger.info("Запуск бота")

    asyncio.run(main())
