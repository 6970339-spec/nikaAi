from aiogram.fsm.state import State, StatesGroup


class Questionnaire(StatesGroup):
    age = State()
    location = State()
    nationality = State()
    aqida_manhaj = State()
    marital_status = State()
    children = State()
    polygyny_attitude = State()
    free_text = State()
    preview = State()
