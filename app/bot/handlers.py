from __future__ import annotations

import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.types.input_file import FSInputFile
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.bot.states import Questionnaire
from app.db.models import Profile, User
from app.db.session import SessionFactory

router = Router()
logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parents[1]
BROTHER_IMG = APP_DIR / "brother.png"
SISTER_IMG = APP_DIR / "sister.png"


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Заполнить/обновить анкету")],
            [KeyboardButton(text="👤 Моя анкета")],
            [KeyboardButton(text="🔎 Найти")],
        ],
        resize_keyboard=True,
        selective=True,
    )


def gender_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Я брат", callback_data="gender:BROTHER"),
                InlineKeyboardButton(text="Я сестра", callback_data="gender:SISTER"),
            ]
        ]
    )


def kb_from_rows(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t, callback_data=c) for (t, c) in row]
            for row in rows
        ]
    )


def nationality_kb() -> InlineKeyboardMarkup:
    return kb_from_rows([
        [("Таджик(ка)", "nat:Таджик(ка)"), ("Узбек(ка)", "nat:Узбек(ка)")],
        [("Казах(ка)", "nat:Казах(ка)"), ("Киргиз(ка)", "nat:Киргиз(ка)")],
        [("Татар(ка)", "nat:Татар(ка)"), ("Русский(ая) мусульманин(ка)", "nat:Русский(ая) мусульманин(ка)")],
        [("Другое (написать)", "nat:OTHER")],
    ])


def marital_status_kb() -> InlineKeyboardMarkup:
    return kb_from_rows([
        [("Никогда не был(а) в браке", "ms:Никогда")],
        [("Разведён(а)", "ms:Разведён(а)"), ("Вдовец/вдова", "ms:Вдовец/вдова")],
    ])


def children_kb() -> InlineKeyboardMarkup:
    return kb_from_rows([
        [("Нет", "ch:Нет")],
        [("Да, живут со мной", "ch:Да, со мной")],
        [("Да, живут отдельно", "ch:Да, отдельно")],
    ])


def prayer_kb() -> InlineKeyboardMarkup:
    return kb_from_rows([
        [("Да, регулярно", "pr:Регулярно")],
        [("Иногда", "pr:Иногда")],
        [("Пока нет, но хочу", "pr:Хочу начать")],
    ])


def relocation_kb() -> InlineKeyboardMarkup:
    return kb_from_rows([
        [("Да", "rel:Да"), ("Нет", "rel:Нет")],
        [("Зависит от обстоятельств", "rel:Зависит")],
    ])


def name_kb() -> InlineKeyboardMarkup:
    return kb_from_rows([
        [("Скрыть имя (при знакомстве)", "name:HIDE")],
    ])


def partner_nat_kb() -> InlineKeyboardMarkup:
    return kb_from_rows([
        [("Не имеет значения", "pn:Не имеет значения")],
        [("Та же, что у меня", "pn:Та же, что у меня")],
        [("Конкретно указать", "pn:CONCRETE")],
    ])


def partner_priority_kb() -> InlineKeyboardMarkup:
    return kb_from_rows([
        [("Религиозность", "pp:Религиозность"), ("Характер и уважение", "pp:Характер и уважение")],
        [("Семейные ценности", "pp:Семейные ценности"), ("Всё вместе", "pp:Всё вместе")],
    ])


def preview_kb() -> InlineKeyboardMarkup:
    return kb_from_rows([
        [("✅ Подтвердить", "profile:confirm")],
        [("✏️ Изменить", "profile:edit")],
    ])


def my_profile_kb() -> InlineKeyboardMarkup:
    return kb_from_rows([
        [("👀 Смотреть", "myprofile:view"), ("✏️ Изменить", "myprofile:edit")],
    ])


def icon_path(gender: str | None) -> Path | None:
    if gender == "BROTHER":
        return BROTHER_IMG
    if gender == "SISTER":
        return SISTER_IMG
    return None


def gender_label(gender: str | None) -> str:
    return "Брат" if gender == "BROTHER" else ("Сестра" if gender == "SISTER" else "")


async def get_or_create_user(tg_id: int, username: str | None) -> User:
    async with SessionFactory() as session:
        res = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = res.scalar_one_or_none()
        if user is None:
            user = User(telegram_id=tg_id, username=username)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            user.username = username
            await session.commit()
        return user


async def get_user(tg_id: int) -> User | None:
    async with SessionFactory() as session:
        res = await session.execute(select(User).where(User.telegram_id == tg_id))
        return res.scalar_one_or_none()


async def ensure_gender_or_ask(message: Message, state: FSMContext) -> User | None:
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    if not user.gender:
        await state.clear()
        await message.answer("Ассаляму алейкум.\n\nПеред началом выберите, кто вы:", reply_markup=gender_kb())
        return None
    return user


async def start_questionnaire(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Questionnaire.name)
    await message.answer(
        "1) 👤 Как вас зовут? Можете написать имя или скрыть до знакомства.",
        reply_markup=name_kb(),
    )


def build_preview_text(gender: str, data: dict) -> tuple[str, str, str]:
    about_lines = [
        f"👤 Имя: {data.get('name', '-')}",
        f"🎂 Возраст: {data.get('age', '-')}",
        f"🌍 Национальность: {data.get('nationality', '-')}",
        f"🏙️ Город/страна: {data.get('city', '-')}",
        f"💍 Статус: {data.get('marital_status', '-')}",
        f"👶 Дети: {data.get('children', '-')}",
        f"🕌 Намаз: {data.get('prayer', '-')}",
        f"🧳 Переезд: {data.get('relocation', '-')}",
        f"📩 Контакты (скрыты): {data.get('contact_info', '-')}",
    ]
    extra = (data.get("extra_about") or "").strip()
    if extra:
        about_lines.append(f"О себе: {extra}")

    looking_lines = [
        f"🎂 Возраст: {data.get('partner_age', '-')}",
        f"🌍 Национальность: {data.get('partner_nationality_pref', '-')}",
        f"⭐ Самое важное: {data.get('partner_priority', '-')}",
    ]

    about_text = "\n".join(about_lines)
    looking_text = "\n".join(looking_lines)

    pretty = (
        "Проверьте анкету перед сохранением:\n\n"
        f"🧑‍⚖️ Вы: {gender_label(gender)}\n\n"
        "🟦 О себе:\n"
        f"{about_text}\n\n"
        "🟩 Кого ищу:\n"
        f"{looking_text}\n"
    )
    return about_text, looking_text, pretty


async def send_icon_if_exists(message: Message, gender: str | None) -> None:
    p = icon_path(gender)
    if p and p.exists():
        await message.answer_photo(FSInputFile(p))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    if not user.gender:
        await state.clear()
        await message.answer("Ассаляму алейкум.\n\nВыберите, кто вы:", reply_markup=gender_kb())
        return
    await message.answer("Ассаляму алейкум.\n\nВыберите действие:", reply_markup=main_kb())


@router.callback_query(F.data.startswith("gender:"))
async def on_gender(call: CallbackQuery, state: FSMContext) -> None:
    gender = call.data.split(":", 1)[1]
    tg_id = call.from_user.id

    async with SessionFactory() as session:
        res = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = res.scalar_one_or_none()
        if user is None:
            user = User(telegram_id=tg_id, username=call.from_user.username, gender=gender)
            session.add(user)
        else:
            user.gender = gender
            user.username = call.from_user.username
        await session.commit()

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    img = icon_path(gender)
    if img and img.exists():
        await call.message.answer_photo(FSInputFile(img))

    await call.message.answer("Хорошо. Я задам несколько коротких вопросов.")
    await call.answer()
    await start_questionnaire(call.message, state)


@router.message(Command("profile"))
@router.message(F.text == "📝 Заполнить/обновить анкету")
async def start_profile(message: Message, state: FSMContext) -> None:
    user = await ensure_gender_or_ask(message, state)
    if user is None:
        return
    await start_questionnaire(message, state)


@router.callback_query(Questionnaire.name, F.data == "name:HIDE")
async def q_name_hide(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(name="Скрыто")
    await state.set_state(Questionnaire.age)
    await call.message.answer("2) 🎂 Сколько вам лет? (напишите число, например 27)")
    await call.answer()


@router.message(Questionnaire.name)
async def q_name(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Введите имя (минимум 2 символа) или выберите вариант скрыть имя.")
        return
    await state.update_data(name=text)
    await state.set_state(Questionnaire.age)
    await message.answer("2) 🎂 Сколько вам лет? (напишите число, например 27)")


@router.message(Questionnaire.age)
async def q_age(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or not (16 <= int(text) <= 80):
        await message.answer("Введите возраст числом (пример: 27). Диапазон 16–80.")
        return

    await state.update_data(age=text)
    await state.set_state(Questionnaire.nationality)
    await message.answer("3) 🌍 Ваша национальность:", reply_markup=nationality_kb())


@router.callback_query(Questionnaire.nationality, F.data.startswith("nat:"))
async def q_nationality(call: CallbackQuery, state: FSMContext) -> None:
    val = call.data.split(":", 1)[1]
    if val == "OTHER":
        await state.set_state(Questionnaire.nationality_other)
        await call.message.answer("🌍 Напишите вашу национальность (свободно):")
        await call.answer()
        return

    await state.update_data(nationality=val)
    await state.set_state(Questionnaire.city)
    await call.message.answer("4) 🏙️ Где вы живёте сейчас? (город, страна)")
    await call.answer()


@router.message(Questionnaire.nationality_other)
async def q_nationality_other(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Напишите национальность чуть понятнее (минимум 2 символа).")
        return

    await state.update_data(nationality=text)
    await state.set_state(Questionnaire.city)
    await message.answer("4) 🏙️ Где вы живёте сейчас? (город, страна)")


@router.message(Questionnaire.city)
async def q_city(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Укажите город/страну (минимум 2 символа).")
        return

    await state.update_data(city=text)
    await state.set_state(Questionnaire.marital_status)
    await message.answer("5) 💍 Ваш текущий семейный статус:", reply_markup=marital_status_kb())


@router.callback_query(Questionnaire.marital_status, F.data.startswith("ms:"))
async def q_marital(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(marital_status=call.data.split(":", 1)[1])
    await state.set_state(Questionnaire.children)
    await call.message.answer("6) 👶 Есть ли у вас дети?", reply_markup=children_kb())
    await call.answer()


@router.callback_query(Questionnaire.children, F.data.startswith("ch:"))
async def q_children(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(children=call.data.split(":", 1)[1])
    await state.set_state(Questionnaire.prayer)
    await call.message.answer("7) 🕌 Совершаете ли вы намаз?", reply_markup=prayer_kb())
    await call.answer()


@router.callback_query(Questionnaire.prayer, F.data.startswith("pr:"))
async def q_prayer(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(prayer=call.data.split(":", 1)[1])
    await state.set_state(Questionnaire.relocation)
    await call.message.answer("8) 🧳 Рассматриваете ли вы переезд после брака?", reply_markup=relocation_kb())
    await call.answer()


@router.callback_query(Questionnaire.relocation, F.data.startswith("rel:"))
async def q_relocation(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(relocation=call.data.split(":", 1)[1])
    await state.set_state(Questionnaire.extra_about)
    await call.message.answer("9) ✍️ Коротко о себе (1–3 предложения). Если не хотите — напишите: пропустить")
    await call.answer()


@router.message(Questionnaire.extra_about)
async def q_extra(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text.lower() == "пропустить":
        text = ""
    await state.update_data(extra_about=text)

    await state.set_state(Questionnaire.partner_age)
    await message.answer("10) 🎂 Примерный возраст будущего супруга(и)? (например 22–28)")


@router.message(Questionnaire.partner_age)
async def q_partner_age(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Укажите возраст/диапазон (например 22–28).")
        return
    await state.update_data(partner_age=text)
    await state.set_state(Questionnaire.partner_nationality_pref)
    await message.answer("11) 🌍 Национальность будущего супруга(и):", reply_markup=partner_nat_kb())


@router.callback_query(Questionnaire.partner_nationality_pref, F.data.startswith("pn:"))
async def q_partner_nat(call: CallbackQuery, state: FSMContext) -> None:
    val = call.data.split(":", 1)[1]
    if val == "CONCRETE":
        await state.set_state(Questionnaire.partner_nationality_custom)
        await call.message.answer("🌍 Напишите национальность, которую вы предпочитаете (или несколько):")
        await call.answer()
        return

    await state.update_data(partner_nationality_pref=val)
    await state.set_state(Questionnaire.partner_priority)
    await call.message.answer("12) ⭐ Что для вас самое важное в будущем супруге(е)?", reply_markup=partner_priority_kb())
    await call.answer()


@router.message(Questionnaire.partner_nationality_custom)
async def q_partner_nat_custom(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Напишите чуть понятнее (минимум 2 символа).")
        return
    await state.update_data(partner_nationality_pref=text)
    await state.set_state(Questionnaire.partner_priority)
    await message.answer("12) ⭐ Что для вас самое важное в будущем супруге(е)?", reply_markup=partner_priority_kb())


@router.callback_query(Questionnaire.partner_priority, F.data.startswith("pp:"))
async def q_partner_priority(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(partner_priority=call.data.split(":", 1)[1])
    await state.set_state(Questionnaire.contact_info)
    await call.message.answer(
        "13) 📞 Напишите контакты для связи (номер, Telegram, email и т.п.).\n"
        "Контакты не отображаются в поиске и видны только администратору.",
    )
    await call.answer()


@router.message(Questionnaire.contact_info)
async def q_contact_info(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 3:
        await message.answer("Укажите контакт понятнее (минимум 3 символа).")
        return
    await state.update_data(contact_info=text)
    await state.set_state(Questionnaire.preview)

    user = await get_user(message.from_user.id)
    gender = user.gender if user and user.gender else "BROTHER"

    data = await state.get_data()
    _about_text, _looking_text, pretty = build_preview_text(gender, data)

    await send_icon_if_exists(message, gender)
    await message.answer(pretty, reply_markup=preview_kb())


@router.callback_query(Questionnaire.preview, F.data == "profile:edit")
async def preview_edit(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await call.message.answer("Ок. Заполним анкету заново.")
    await start_questionnaire(call.message, state)


@router.callback_query(Questionnaire.preview, F.data == "profile:confirm")
async def preview_confirm(call: CallbackQuery, state: FSMContext) -> None:
    # важно: сразу отвечаем, чтобы Telegram не показывал “ошибка на сервере”
    await call.answer("Сохраняю...")

    try:
        user = await get_user(call.from_user.id)
        if not user or not user.gender:
            await call.message.answer("Сначала выберите: вы брат или сестра.", reply_markup=gender_kb())
            await state.clear()
            return

        data = await state.get_data()
        about_text, looking_text, _pretty = build_preview_text(user.gender, data)

        async with SessionFactory() as session:
            res = await session.execute(select(User).where(User.telegram_id == call.from_user.id))
            db_user = res.scalar_one_or_none()
            if db_user is None:
                db_user = User(
                    telegram_id=call.from_user.id,
                    username=call.from_user.username,
                    gender=user.gender,
                )
                session.add(db_user)
                await session.flush()

            profile = Profile(
                user_id=db_user.id,
                age=data.get("age"),
                nationality=data.get("nationality"),
                city=data.get("city"),
                marital_status=data.get("marital_status"),
                children=data.get("children"),
                prayer=data.get("prayer"),
                relocation=data.get("relocation"),
                name=data.get("name"),
                extra_about=(data.get("extra_about") or "").strip(),
                partner_age=data.get("partner_age"),
                partner_nationality_pref=data.get("partner_nationality_pref"),
                partner_priority=data.get("partner_priority"),
                contact_info=data.get("contact_info"),
                about_me_text=about_text,
                looking_for_text=looking_text,
                status="ACTIVE",
            )
            session.add(profile)
            await session.commit()

        await state.clear()
        await call.message.answer("✅ Анкета сохранена.\n\nНажмите: 🔎 Найти", reply_markup=main_kb())

    except SQLAlchemyError as e:
        logger.exception("DB error on confirm: %s", e)
        await call.message.answer("Ошибка базы при сохранении анкеты. Посмотрите Traceback в консоли PyCharm.")
    except Exception as e:
        logger.exception("Unexpected error on confirm: %s", e)
        await call.message.answer("Ошибка при сохранении анкеты. Посмотрите Traceback в консоли PyCharm.")


@router.message(Command("find"))
@router.message(F.text == "🔎 Найти")
async def find_handler(message: Message, state: FSMContext) -> None:
    user = await ensure_gender_or_ask(message, state)
    if user is None:
        return

    target_gender = "SISTER" if user.gender == "BROTHER" else "BROTHER"

    async with SessionFactory() as session:
        stmt = (
            select(Profile, User)
            .join(User, User.id == Profile.user_id)
            .where(
                Profile.status == "ACTIVE",
                User.gender == target_gender,
                User.telegram_id != message.from_user.id,
            )
            .order_by(Profile.created_at.desc())
            .limit(5)
        )
        rows = (await session.execute(stmt)).all()

    if not rows:
        await message.answer("Пока нет анкет подходящего пола в базе.\nДля теста создайте анкету с другого аккаунта.")
        return

    await message.answer("🔎 Результаты поиска (ник/username скрыт):")

    for profile, u in rows:
        img = icon_path(u.gender)
        caption = (
            f"Анкета #{profile.id}\n"
            f"🧑‍⚖️ {gender_label(u.gender)}\n\n"
            f"👤 Имя: {profile.name or '-'}\n"
            f"🎂 Возраст: {profile.age or '-'}\n"
            f"🌍 Национальность: {profile.nationality or '-'}\n"
            f"🏙️ Город: {profile.city or '-'}\n"
            f"💍 Статус: {profile.marital_status or '-'}\n"
            f"👶 Дети: {profile.children or '-'}\n"
            f"🕌 Намаз: {profile.prayer or '-'}\n"
            f"🧳 Переезд: {profile.relocation or '-'}\n\n"
            f"✍️ О себе: {(profile.extra_about or '').strip() or '-'}\n"
            "🔒 Контакты скрыты\n"
        )
        if img and img.exists():
            await message.answer_photo(FSInputFile(img), caption=caption[:1024])
        else:
            await message.answer(caption)

    await message.answer("✨ Это все найденные анкеты. Хотите обновить свою? Нажмите 👤 Моя анкета.")


@router.message(Command("my_profile"))
@router.message(F.text == "👤 Моя анкета")
async def my_profile(message: Message, state: FSMContext) -> None:
    user = await ensure_gender_or_ask(message, state)
    if user is None:
        return

    async with SessionFactory() as session:
        stmt = (
            select(Profile)
            .where(Profile.user_id == user.id)
            .order_by(Profile.created_at.desc())
            .limit(1)
        )
        profile = (await session.execute(stmt)).scalar_one_or_none()

    if profile is None:
        await message.answer("У вас пока нет анкеты. Нажмите: 📝 Заполнить/обновить анкету")
        return

    caption = (
        "🧾 Ваша анкета:\n\n"
        f"👤 Имя: {profile.name or '-'}\n"
        f"🎂 Возраст: {profile.age or '-'}\n"
        f"🌍 Национальность: {profile.nationality or '-'}\n"
        f"🏙️ Город: {profile.city or '-'}\n"
        f"💍 Статус: {profile.marital_status or '-'}\n"
        f"👶 Дети: {profile.children or '-'}\n"
        f"🕌 Намаз: {profile.prayer or '-'}\n"
        f"🧳 Переезд: {profile.relocation or '-'}\n"
        f"✍️ О себе: {(profile.extra_about or '').strip() or '-'}\n"
        f"🎯 Ищу возраст: {profile.partner_age or '-'}\n"
        f"🌍 Ищу национальность: {profile.partner_nationality_pref or '-'}\n"
        f"⭐ Главное: {profile.partner_priority or '-'}\n"
        f"📩 Контакты (скрыты): {profile.contact_info or '-'}\n"
        "🔒 Контакты не отображаются в поиске."
    )
    await message.answer(caption, reply_markup=my_profile_kb())


@router.callback_query(F.data == "myprofile:view")
async def my_profile_view(call: CallbackQuery) -> None:
    await call.answer("Анкета показана.")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@router.callback_query(F.data == "myprofile:edit")
async def my_profile_edit(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await call.message.answer("Ок. Заполним анкету заново.")
    await start_questionnaire(call.message, state)


@router.message()
async def fallback(message: Message) -> None:
    await message.answer("Используйте кнопки меню или /start", reply_markup=main_kb())
