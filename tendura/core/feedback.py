"""Шкалы субъективной оценки тренировки Training Endurance."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeedbackOption:
    display_value: int
    api_value: int
    name: str
    description: str


FEELING_OPTIONS = (
    FeedbackOption(1, 5, "Ужасно", "Болезнь, травма или полное истощение. Тренировку лучше было пропустить."),
    FeedbackOption(2, 15, "Очень плохо", "Сильная усталость, недомогание, всё давалось с огромным трудом."),
    FeedbackOption(3, 25, "Плохо", "Тяжёлые ноги, отсутствие энергии, пришлось заставлять себя."),
    FeedbackOption(4, 35, "Ниже среднего", "Вялость, не было желания тренироваться, темп давался тяжелее обычного."),
    FeedbackOption(5, 45, "Средне", "Обычное состояние, ничего особенного — ни хорошо, ни плохо."),
    FeedbackOption(6, 55, "Неплохо", "Нормальное самочувствие, тренировка прошла без проблем."),
    FeedbackOption(7, 65, "Хорошо", "Чувствовали себя бодро, нагрузка давалась легче обычного."),
    FeedbackOption(8, 75, "Очень хорошо", "Много энергии, лёгкость в движениях, хотелось тренироваться."),
    FeedbackOption(9, 85, "Отлично", "Прилив сил, всё получалось, ощущение полёта."),
    FeedbackOption(10, 95, "Превосходно", "Идеальное состояние, пиковая форма, редкое ощущение абсолютной лёгкости."),
)

EXERTION_OPTIONS = (
    FeedbackOption(1, 1, "Не ощущаю нагрузку", "Соответствует минимальной зоне интенсивности."),
    FeedbackOption(2, 2, "Очень легко", "Лёгкая восстановительная нагрузка, не требует усилий."),
    FeedbackOption(3, 3, "Легко", "Можно разговаривать без одышки, нагрузка начинает ощущаться, но пока ещё легко."),
    FeedbackOption(4, 4, "Умеренная нагрузка", "Соответствует порогу 1: говорить легко, но появляется небольшая одышка."),
    FeedbackOption(5, 5, "Предпороговая нагрузка", "Между двумя порогами: можно говорить с лёгкой одышкой, минимум 90 минут."),
    FeedbackOption(6, 6, "Пороговая нагрузка", "Соответствует порогу 2: можно говорить с одышкой, минимум 50 минут."),
    FeedbackOption(7, 7, "Тяжёлая нагрузка", "Между порогом 2 и VO₂max: говорить сложно, только фразами, минимум 30 минут."),
    FeedbackOption(8, 8, "Очень тяжёлая нагрузка", "Соответствует VO₂max: разговаривать почти невозможно из-за сильной одышки."),
    FeedbackOption(9, 9, "Максимальная нагрузка", "Сильная одышка, тяжело дышать, максимальные зоны интенсивности."),
    FeedbackOption(10, 10, "Спринтерское усилие", "Такую нагрузку можно поддерживать менее одной минуты."),
)


def option_by_display_value(
    options: tuple[FeedbackOption, ...], value: int
) -> FeedbackOption | None:
    return next((option for option in options if option.display_value == value), None)


def option_by_api_value(
    options: tuple[FeedbackOption, ...], value: int | None
) -> FeedbackOption | None:
    return next((option for option in options if option.api_value == value), None)
