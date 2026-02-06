from __future__ import annotations

import asyncio
import logging
import random
from pathlib import Path
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
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

from app.ai.attribute_extractor import extract_profile_attributes_free_text_async
from app.bot.states import Questionnaire
from app.db.attribute_service import map_extracted_item_to_attribute, get_attribute_by_key, upsert_profile_attribute_value
from app.db.models import Profile, User
from app.db.session import SessionFactory

router = Router()
logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parents[1]
BROTHER_IMG = APP_DIR / "brother.png"
SISTER_IMG = APP_DIR / "sister.png"

AQIDA_LABELS = {
    "AHLU_SUNNA": "Ахлю-Сунна",
    "SALAFI": "Саляфи",
    "OTHER": "Другое",
    "UNKNOWN": "Не знаю",
}

MARITAL_LABELS = {
    "NEVER_MARRIED": "Не был(а) женат(а)",
    "MARRIED": "Женат/замужем",
    "DIVORCED": "В разводе",
    "WIDOWED": "Вдовец/вдова",
}

CHILDREN_LABELS = {
    "NONE": "Нет",
    "HAS_1": "Есть: 1",
    "HAS_2": "Есть: 2",
    "HAS_3PLUS": "Есть: 3+",
    "UNKNOWN": "Не хочу указывать",
}

POLYGYNY_LABELS_BROTHER = {
    "MONOGAMY_ONLY": "Хочу только единобрачие",
    "OPEN_TO_POLYGYNY": "Допускаю многоженство",
    "SEEKS_POLYGYNY": "Хочу/планирую многоженство",
    "NEUTRAL": "Не важно/не обсуждал",
}

POLYGYNY_LABELS_SISTER = {
    "MONOGAMY_ONLY": "Хочу только единобрачие",
    "OPEN_TO_POLYGYNY": "Допускаю многоженство",
    "NEUTRAL": "Не важно/не обсуждала",
}


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🎲 Быстро заполнить (брат)"),
                KeyboardButton(text="🎲 Быстро заполнить (сестра)"),
            ],
            [KeyboardButton(text="📝 Заполнить/обновить анкету")],
            [KeyboardButton(text="👤 Моя анкета")],
            [KeyboardButton(text="🔍 Найти")],
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


def aqida_kb() -> InlineKeyboardMarkup:
    return kb_from_rows(
        [
            [("Ахлю-Сунна", "aq:AHLU_SUNNA"), ("Саляфи", "aq:SALAFI")],
            [("Другое", "aq:OTHER"), ("Не знаю", "aq:UNKNOWN")],
        ]
    )


def marital_status_kb() -> InlineKeyboardMarkup:
    return kb_from_rows(
        [
            [("Не был(а) женат(а)", "ms:NEVER_MARRIED")],
            [("Женат/замужем", "ms:MARRIED")],
            [("В разводе", "ms:DIVORCED"), ("Вдовец/вдова", "ms:WIDOWED")],
        ]
    )


def children_kb() -> InlineKeyboardMarkup:
    return kb_from_rows(
        [
            [("Нет", "ch:NONE"), ("Есть: 1", "ch:HAS_1")],
            [("Есть: 2", "ch:HAS_2"), ("Есть: 3+", "ch:HAS_3PLUS")],
            [("Не хочу указывать", "ch:UNKNOWN")],
        ]
    )


def polygyny_kb(gender: str | None) -> InlineKeyboardMarkup:
    if gender == "SISTER":
        rows = [
            [("Хочу только единобрачие", "poly:MONOGAMY_ONLY")],
            [("Допускаю многоженство", "poly:OPEN_TO_POLYGYNY")],
            [("Не важно/не обсуждала", "poly:NEUTRAL")],
        ]
    else:
        rows = [
            [("Хочу только единобрачие", "poly:MONOGAMY_ONLY")],
            [("Допускаю многоженство", "poly:OPEN_TO_POLYGYNY")],
            [("Хочу/планирую многоженство", "poly:SEEKS_POLYGYNY")],
            [("Не важно/не обсуждал", "poly:NEUTRAL")],
        ]
    return kb_from_rows(rows)


def preview_kb() -> InlineKeyboardMarkup:
    return kb_from_rows(
        [
            [("✅ Подтвердить", "profile:confirm")],
            [("✏️ Изменить", "profile:edit")],
        ]
    )


def my_profile_kb() -> InlineKeyboardMarkup:
    return kb_from_rows(
        [
            [("👀 Смотреть", "myprofile:view"), ("✏️ Изменить", "myprofile:edit")],
        ]
    )


def icon_path(gender: str | None) -> Path | None:
    if gender == "BROTHER":
        return BROTHER_IMG
    if gender == "SISTER":
        return SISTER_IMG
    return None


def gender_label(gender: str | None) -> str:
    return "Брат" if gender == "BROTHER" else ("Сестра" if gender == "SISTER" else "")


def _label(value: str | None, mapping: dict[str, str]) -> str:
    if not value:
        return "-"
    return mapping.get(value, value)


def _short(text: str | None, limit: int = 300) -> str:
    text = (text or "").strip()
    if not text:
        return "-"
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def build_preview_text(data: dict) -> str:
    free_text = _short(data.get("free_text"))
    lines = [
        "Проверьте анкету перед сохранением:\n",
        f"🎂 <b>Возраст:</b> {data.get('age', '-')}",
        f"📍 <b>Локация:</b> {data.get('location', '-')}",
        f"🌍 <b>Национальность:</b> {data.get('nationality', '-')}",
        f"🕌 <b>Акъыда/манхадж:</b> {_label(data.get('aqida_manhaj'), AQIDA_LABELS)}",
        f"💍 <b>Семейное положение:</b> {_label(data.get('marital_status'), MARITAL_LABELS)}",
        f"👶 <b>Дети:</b> {_label(data.get('children'), CHILDREN_LABELS)}",
        f"👫 <b>Отношение к многоженству:</b> {data.get('polygyny_label', '-')}",
        "──────────────────",
        f"✍️ <b>О себе:</b> {free_text}",
    ]
    return "\n".join(lines)


def random_profile_data(gender: str | None) -> dict[str, Any]:
    nationalities = [
        "Таджик(ка)",
        "Узбек(ка)",
        "Казах(ка)",
        "Киргиз(ка)",
        "Татар(ка)",
        "Русский(ая) мусульманин(ка)",
    ]
    locations = [
        "Москва, Россия",
        "Ташкент, Узбекистан",
        "Душанбе, Таджикистан",
        "Алматы, Казахстан",
    ]
    aqida_codes = list(AQIDA_LABELS.keys())
    marital_codes = list(MARITAL_LABELS.keys())
    children_codes = list(CHILDREN_LABELS.keys())
    polygyny_codes = list(
        (POLYGYNY_LABELS_SISTER if gender == "SISTER" else POLYGYNY_LABELS_BROTHER).keys()
    )

    return {
        "age": str(random.randint(18, 40)),
        "location": random.choice(locations),
        "nationality": random.choice(nationalities),
        "aqida_manhaj": random.choice(aqida_codes),
        "marital_status": random.choice(marital_codes),
        "children": random.choice(children_codes),
        "polygyny_attitude": random.choice(polygyny_codes),
        "free_text": "Люблю читать, развиваться, ценю искренность и уважение. "
        "Ищу серьезные намерения и общие ценности.",
    }


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


async def update_user_gender(tg_id: int, username: str | None, gender: str) -> User:
    async with SessionFactory() as session:
        res = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = res.scalar_one_or_none()
        if user is None:
            user = User(telegram_id=tg_id, username=username, gender=gender)
            session.add(user)
        else:
            user.gender = gender
            user.username = username
        await session.commit()
        await session.refresh(user)
        return user


async def create_profile_for_user(user: User, data: dict) -> int:
    async with SessionFactory() as session:
        res = await session.execute(select(User).where(User.telegram_id == user.telegram_id))
        db_user = res.scalar_one_or_none()
        if db_user is None:
            db_user = User(
                telegram_id=user.telegram_id,
                username=user.username,
                gender=user.gender,
            )
            session.add(db_user)
            await session.flush()

        profile = Profile(
            user_id=db_user.id,
            age=data.get("age"),
            nationality=data.get("nationality"),
            city=data.get("location"),
            marital_status=data.get("marital_status"),
            children=data.get("children"),
            aqida=data.get("aqida_manhaj"),
            polygyny=data.get("polygyny_attitude"),
            about_me_text=(data.get("free_text") or "").strip(),
            status="ACTIVE",
        )
        session.add(profile)
        await session.flush()

        canonical_keys = [
            "age",
            "location",
            "nationality",
            "aqida_manhaj",
            "marital_status",
            "children",
            "polygyny_attitude",
        ]
        enum_keys = {"aqida_manhaj", "marital_status", "children", "polygyny_attitude"}
        for key in canonical_keys:
            attr = await get_attribute_by_key(session, key)
            if attr is None:
                continue
            value = data.get(key)
            if not value:
                continue
            option_code = value if key in enum_keys else None
            await upsert_profile_attribute_value(
                session=session,
                profile_id=profile.id,
                attribute=attr,
                value=str(value),
                option_code=option_code,
                confidence=1.0,
                evidence=None,
            )

        await session.commit()
        return profile.id


async def extract_and_persist(profile_id: int, free_text: str) -> None:
    if not free_text or len(free_text) < 10:
        return
    try:
        items = await extract_profile_attributes_free_text_async(free_text)
    except Exception:
        logger.exception("AI attribute extraction failed")
        return

    async with SessionFactory() as session:
        for item in items:
            try:
                attribute, normalized = await map_extracted_item_to_attribute(session, item)
                value = str(normalized.get("value", "")).strip()
                if not value:
                    continue
                confidence = float(normalized.get("confidence", 1.0))
                evidence = normalized.get("evidence")
                await upsert_profile_attribute_value(
                    session=session,
                    profile_id=profile_id,
                    attribute=attribute,
                    value=value,
                    option_code=None,
                    confidence=confidence,
                    evidence=evidence,
                )
            except Exception:
                logger.exception("Failed to persist extracted item: %s", item)
        await session.commit()


async def ensure_gender_or_ask(message: Message, state: FSMContext) -> User | None:
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    if not user.gender:
        await state.clear()
        await message.answer(
            "Ассаляму алейкум.\n\nПеред началом выберите, кто вы:",
            reply_markup=gender_kb(),
        )
        return None
    return user


async def start_questionnaire(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Questionnaire.age)
    await message.answer("1) 🎂 Сколько вам лет? (16–80)")


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


async def handle_quick_fill(message: Message, state: FSMContext, gender: str) -> None:
    await state.clear()
    user = await update_user_gender(message.from_user.id, message.from_user.username, gender)
    data = random_profile_data(gender)
    profile_id = await create_profile_for_user(user, data)
    asyncio.create_task(extract_and_persist(profile_id, data.get("free_text") or ""))

    pretty = build_preview_text(
        {
            **data,
            "polygyny_label": _label(
                data.get("polygyny_attitude"),
                POLYGYNY_LABELS_SISTER if gender == "SISTER" else POLYGYNY_LABELS_BROTHER,
            ),
        }
    )
    await send_icon_if_exists(message, user.gender)
    await message.answer(
        "✅ Анкета создана автоматически.\n\n"
        f"{pretty}\n"
        "Нажмите: 🔍 Найти",
        reply_markup=main_kb(),
        parse_mode="HTML",
    )


@router.message(F.text == "🎲 Быстро заполнить (брат)")
async def quick_fill_brother(message: Message, state: FSMContext) -> None:
    await handle_quick_fill(message, state, "BROTHER")


@router.message(F.text == "🎲 Быстро заполнить (сестра)")
async def quick_fill_sister(message: Message, state: FSMContext) -> None:
    await handle_quick_fill(message, state, "SISTER")


@router.message(Questionnaire.age)
async def q_age(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or not (16 <= int(text) <= 80):
        await message.answer("Введите возраст числом (пример: 27). Диапазон 16–80.")
        return

    await state.update_data(age=text)
    await state.set_state(Questionnaire.location)
    await message.answer("2) 📍 Где вы живете сейчас? (город, страна)")


@router.message(Questionnaire.location)
async def q_location(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Укажите локацию (минимум 2 символа).")
        return

    await state.update_data(location=text)
    await state.set_state(Questionnaire.nationality)
    await message.answer("3) 🌍 Ваша национальность/этнос?")


@router.message(Questionnaire.nationality)
async def q_nationality(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Укажите национальность (минимум 2 символа).")
        return

    await state.update_data(nationality=text)
    await state.set_state(Questionnaire.aqida_manhaj)
    await message.answer("4) 🕌 Ваша акъыда/манхадж:", reply_markup=aqida_kb())


@router.callback_query(Questionnaire.aqida_manhaj, F.data.startswith("aq:"))
async def q_aqida(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(aqida_manhaj=call.data.split(":", 1)[1])
    await state.set_state(Questionnaire.marital_status)
    await call.message.answer("5) 💍 Ваш семейный статус:", reply_markup=marital_status_kb())
    await call.answer()


@router.callback_query(Questionnaire.marital_status, F.data.startswith("ms:"))
async def q_marital(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(marital_status=call.data.split(":", 1)[1])
    await state.set_state(Questionnaire.children)
    await call.message.answer("6) 👶 Есть ли у вас дети?", reply_markup=children_kb())
    await call.answer()


@router.callback_query(Questionnaire.children, F.data.startswith("ch:"))
async def q_children(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(children=call.data.split(":", 1)[1])
    await state.set_state(Questionnaire.polygyny_attitude)
    user = await get_user(call.from_user.id)
    gender = user.gender if user else None
    await call.message.answer(
        "7) 👫 Отношение к многоженству:",
        reply_markup=polygyny_kb(gender),
    )
    await call.answer()


@router.callback_query(Questionnaire.polygyny_attitude, F.data.startswith("poly:"))
async def q_polygyny(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(polygyny_attitude=call.data.split(":", 1)[1])
    await state.set_state(Questionnaire.free_text)
    await call.message.answer(
        "8) ✍️ Коротко о себе (минимум 30 символов). "
        "Это главное поле для ИИ."
    )
    await call.answer()


@router.message(Questionnaire.free_text)
async def q_free_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 30:
        await message.answer("Текст слишком короткий. Напишите минимум 30 символов.")
        return

    await state.update_data(free_text=text)
    await state.set_state(Questionnaire.preview)

    data = await state.get_data()
    user = await get_user(message.from_user.id)
    gender = user.gender if user else None
    polygyny_label = _label(
        data.get("polygyny_attitude"),
        POLYGYNY_LABELS_SISTER if gender == "SISTER" else POLYGYNY_LABELS_BROTHER,
    )
    data["polygyny_label"] = polygyny_label
    pretty = build_preview_text(data)

    await send_icon_if_exists(message, gender)
    await message.answer(pretty, reply_markup=preview_kb(), parse_mode="HTML")


@router.callback_query(Questionnaire.preview, F.data == "profile:edit")
async def preview_edit(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await call.message.answer("Ок. Заполним анкету заново.")
    await start_questionnaire(call.message, state)


@router.callback_query(Questionnaire.preview, F.data == "profile:confirm")
async def preview_confirm(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer("Сохраняю...")

    try:
        user = await get_user(call.from_user.id)
        if not user or not user.gender:
            await call.message.answer("Сначала выберите: вы брат или сестра.", reply_markup=gender_kb())
            await state.clear()
            return

        data = await state.get_data()
        free_text = (data.get("free_text") or "").strip()
        profile_id = await create_profile_for_user(user, data)

        await state.clear()
        asyncio.create_task(extract_and_persist(profile_id, free_text))

        await call.message.answer(
            "✅ Анкета сохранена.\n\nНажмите: 🔍 Найти",
            reply_markup=main_kb(),
        )

    except SQLAlchemyError as e:
        logger.exception("DB error on confirm: %s", e)
        await call.message.answer(
            "Ошибка базы при сохранении анкеты. Посмотрите Traceback в консоли PyCharm."
        )
    except Exception as e:
        logger.exception("Unexpected error on confirm: %s", e)
        await call.message.answer(
            "Ошибка при сохранении анкеты. Посмотрите Traceback в консоли PyCharm."
        )


@router.message(Command("find"))
@router.message(F.text == "🔍 Найти")
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
        await message.answer(
            "Пока нет анкет подходящего пола в базе.\n"
            "Для теста создайте анкету с другого аккаунта."
        )
        return

    await message.answer("🔍 Результаты поиска (ник/username скрыт):")

    for profile, u in rows:
        img = icon_path(u.gender)
        polygyny_label = _label(
            profile.polygyny,
            POLYGYNY_LABELS_SISTER if u.gender == "SISTER" else POLYGYNY_LABELS_BROTHER,
        )
        caption = (
            f"Анкета #{profile.id}\n"
            f"🧑‍⚕️ {gender_label(u.gender)}\n\n"
            f"🎂 <b>Возраст:</b> {profile.age or '-'}\n"
            f"🌍 <b>Национальность:</b> {profile.nationality or '-'}\n"
            f"💍 <b>Семейное положение:</b> {_label(profile.marital_status, MARITAL_LABELS)}\n"
            f"📍 <b>Локация:</b> {profile.city or '-'}\n"
            f"🕌 <b>Акъыда/манхадж:</b> {_label(profile.aqida, AQIDA_LABELS)}\n"
            f"👶 <b>Дети:</b> {_label(profile.children, CHILDREN_LABELS)}\n"
            f"👫 <b>Многоженство:</b> {polygyny_label}\n"
            "──────────────────\n"
            f"✍️ <b>О себе:</b> {_short(profile.about_me_text)}\n"
        )
        if img and img.exists():
            await message.answer_photo(
                FSInputFile(img),
                caption=caption[:1024],
                parse_mode="HTML",
            )
        else:
            await message.answer(caption, parse_mode="HTML")

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

    polygyny_label = _label(
        profile.polygyny,
        POLYGYNY_LABELS_SISTER if user.gender == "SISTER" else POLYGYNY_LABELS_BROTHER,
    )
    caption = (
        "🧾 Ваша анкета:\n\n"
        f"🎂 <b>Возраст:</b> {profile.age or '-'}\n"
        f"🌍 <b>Национальность:</b> {profile.nationality or '-'}\n"
        f"💍 <b>Семейное положение:</b> {_label(profile.marital_status, MARITAL_LABELS)}\n"
        f"📍 <b>Локация:</b> {profile.city or '-'}\n"
        f"🕌 <b>Акъыда/манхадж:</b> {_label(profile.aqida, AQIDA_LABELS)}\n"
        f"👶 <b>Дети:</b> {_label(profile.children, CHILDREN_LABELS)}\n"
        f"👫 <b>Многоженство:</b> {polygyny_label}\n"
        "──────────────────\n"
        f"✍️ <b>О себе:</b> {_short(profile.about_me_text)}\n"
    )
    await message.answer(caption, reply_markup=my_profile_kb(), parse_mode="HTML")


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
