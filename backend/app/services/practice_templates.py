"""Editable banking starting points, always synthetic and using the same DSL."""

from app.schemas.practice import Definition
from app.services.practice_demo import demo_definition


def template_definition(kind="credit"):
    if kind == "credit":
        return demo_definition()
    labels = {
        "client": ("Открытие карточки клиента", "Mijoz kartasini ochish"),
        "transfer": (
            "Учебный перевод между счетами",
            "Hisoblar orasida oʻquv oʻtkazmasi",
        ),
        "deposit": ("Оформление учебного вклада", "Oʻquv omonatini rasmiylashtirish"),
    }
    ru, uz = labels[kind]

    def l(ru, uz):
        return {"ru": ru, "uz": uz}

    def field(id, type, ru, uz, **kw):
        return {"id": id, "type": type, "label": l(ru, uz), **kw}

    next = field("next", "button", "Продолжить", "Davom etish")
    fields = [
        field(
            "client_code",
            "text",
            "Учебный клиент",
            "Oʻquv mijozi",
            required=True,
            placeholder=l("TEST-001", "TEST-001"),
        )
    ]
    expected = {"client_code": "TEST-001"}
    if kind == "client":
        fields.extend(
            [
                field(
                    "passport_code",
                    "text",
                    "Учебный паспорт",
                    "Oʻquv pasporti",
                    required=True,
                    validation=[{"kind": "passport"}],
                ),
                field(
                    "birth", "date", "Дата рождения", "Tugʻilgan sana", required=True
                ),
            ]
        )
        expected.update(passport_code="AA1234567", birth="2000-01-01")
    else:
        fields.extend(
            [
                field(
                    "account_from",
                    "text",
                    "Учебный счёт",
                    "Oʻquv hisobi",
                    required=True,
                ),
                field(
                    "amount",
                    "number",
                    "Сумма, сум",
                    "Summa, soʻm",
                    required=True,
                    validation=[{"kind": "min", "value": 1}],
                ),
            ]
        )
        expected.update(account_from="TRAIN-001", amount=50000)
        if kind == "transfer":
            fields.append(
                field(
                    "account_to",
                    "text",
                    "Счёт получателя",
                    "Qabul qiluvchi hisobi",
                    required=True,
                )
            )
            expected["account_to"] = "TRAIN-002"
        else:
            fields.append(
                field(
                    "term",
                    "number",
                    "Срок вклада, мес.",
                    "Omonat muddati, oy",
                    required=True,
                )
            )
            expected["term"] = 12
    rules = [
        {
            "id": "check_" + key,
            "condition": {"field": key, "op": "eq", "task_value": True},
            "message": l(
                "Сверьте значение с индивидуальным заданием.",
                "Qiymatni shaxsiy topshiriq bilan solishtiring.",
            ),
            "points": 10,
        }
        for key in expected
    ]
    description = l(
        "Все сведения вымышленные. Используйте только учебные документы.",
        "Barcha maʼlumotlar uydirma. Faqat oʻquv hujjatlaridan foydalaning.",
    )
    task_text = l(
        "Учебные данные: "
        + ", ".join(f"{key}: {value}" for key, value in expected.items()),
        "Oʻquv maʼlumotlari: "
        + ", ".join(f"{key}: {value}" for key, value in expected.items()),
    )
    return Definition.model_validate(
        {
            "title": l(ru, uz),
            "description": description,
            "start": "start",
            "completion": ["result"],
            "tasks": [{"id": "task_1", "description": task_text, "expected": expected}],
            "screens": [
                {
                    "id": "start",
                    "title": l(ru, uz),
                    "description": description,
                    "components": [field("intro", "paragraph", ru, uz), next],
                    "transitions": [{"action": "next", "target": "data"}],
                },
                {
                    "id": "data",
                    "title": l("Заполнение данных", "Maʼlumotlarni kiritish"),
                    "description": description,
                    "components": [*fields, next],
                    "rules": rules,
                    "transitions": [{"action": "next", "target": "review"}],
                },
                {
                    "id": "review",
                    "title": l("Проверка", "Tekshiruv"),
                    "description": description,
                    "components": [
                        field(
                            "summary",
                            "status",
                            "Проверьте данные",
                            "Maʼlumotlarni tekshiring",
                        ),
                        field(
                            "consent",
                            "checkbox",
                            "Подтверждаю учебную операцию",
                            "Oʻquv amaliyotini tasdiqlayman",
                            required=True,
                        ),
                        next,
                    ],
                    "transitions": [{"action": "next", "target": "result"}],
                },
                {
                    "id": "result",
                    "title": l("Операция завершена", "Amaliyot yakunlandi"),
                    "description": description,
                    "components": [
                        field("result_data", "result", "Результат", "Natija")
                    ],
                },
            ],
        }
    )
