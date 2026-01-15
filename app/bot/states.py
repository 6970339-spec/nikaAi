from aiogram.fsm.state import State, StatesGroup


class Questionnaire(StatesGroup):
    # О себе
    name = State()
    age = State()
    nationality = State()
    nationality_other = State()
    city = State()
    marital_status = State()
    children = State()
    prayer = State()
    relocation = State()
    extra_about = State()

    # Кого ищу
    partner_age = State()
    partner_nationality_pref = State()
    partner_nationality_custom = State()
    partner_priority = State()

    preview = State()
