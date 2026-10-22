"""Synthetic scenario, reusable as an editable starting point for authors."""

from app.schemas.practice import Definition


def demo_definition() -> Definition:
    def l(ru, uz):
        return {"ru": ru, "uz": uz}

    def field(id, type, ru, uz, **kw):
        return {"id": id, "type": type, "label": l(ru, uz), **kw}

    def rule(id, field, op, value, ru, uz, points=10):
        return {
            "id": id,
            "condition": {"field": field, "op": op, "value": value},
            "message": l(ru, uz),
            "points": points,
        }

    screens = []

    def screen(id, ru, uz, components, target=None, rules=None, description=None):
        if target:
            components = [
                *components,
                field(
                    "next",
                    "button",
                    "Продолжить",
                    "Davom etish",
                    hint=l(
                        "Проверьте данные и перейдите к следующему шагу.",
                        "Maʼlumotlarni tekshiring va keyingi bosqichga oʻting.",
                    ),
                ),
            ]
        screens.append(
            {
                "id": id,
                "title": l(ru, uz),
                "description": description
                or l(
                    "Учебная операция. Все данные вымышленные.",
                    "Oʻquv amaliyoti. Barcha maʼlumotlar sunʼiy.",
                ),
                "components": components,
                "transitions": [{"action": "next", "target": target}] if target else [],
                "rules": rules or [],
            }
        )

    screen(
        "start",
        "Оформление потребительского кредита",
        "Isteʼmol kreditini rasmiylashtirish",
        [
            field(
                "task",
                "notification",
                "Задание: оформить кредит 12 000 000 сум на 12 месяцев для клиента TEST-001. Выберите учебный паспорт, подтвердите проверку документов и согласие клиента.",
                "Topshiriq: TEST-001 mijoziga 12 oyga 12 000 000 soʻm kredit rasmiylashtiring. Oʻquv pasportini tanlang, hujjatlar tekshiruvi va mijoz roziligini tasdiqlang.",
            )
        ],
        "lending",
    )
    screen(
        "lending",
        "Кредитование",
        "Kreditlash",
        [
            field(
                "applications",
                "table",
                "Учебные заявки",
                "Oʻquv arizalari",
                rows=[{"id": "TRAIN-001", "client": "TEST-002", "status": "draft"}],
            )
        ],
        "search",
    )
    screen(
        "search",
        "Поиск клиента",
        "Mijozni qidirish",
        [
            field(
                "client_id",
                "select",
                "Учебный клиент",
                "Oʻquv mijozi",
                required=True,
                options=[
                    {
                        "value": "TEST-001",
                        "label": l(
                            "TEST-001 · Учебный клиент А", "TEST-001 · Oʻquv mijozi A"
                        ),
                    },
                    {
                        "value": "TEST-002",
                        "label": l(
                            "TEST-002 · Учебный клиент Б", "TEST-002 · Oʻquv mijozi B"
                        ),
                    },
                ],
            )
        ],
        "client",
        [
            rule(
                "correct_client",
                "client_id",
                "eq",
                "TEST-001",
                "Задание выдано для TEST-001. Выберите этого клиента.",
                "Topshiriq TEST-001 uchun. Shu mijozni tanlang.",
            )
        ],
    )
    screen(
        "client",
        "Карточка клиента",
        "Mijoz kartasi",
        [
            field(
                "profile",
                "client",
                "TEST-001 · Учебный клиент А",
                "TEST-001 · Oʻquv mijozi A",
                rows=[
                    {
                        "id": "TEST-001",
                        "document": "TRAIN-PASSPORT-001",
                        "income": "5 000 000 UZS",
                    }
                ],
            )
        ],
        "create",
    )
    screen(
        "create",
        "Создание заявки",
        "Ariza yaratish",
        [
            field(
                "product",
                "select",
                "Продукт",
                "Mahsulot",
                required=True,
                options=[
                    {
                        "value": "consumer",
                        "label": l(
                            "Потребительский кредит (учебный)",
                            "Isteʼmol krediti (oʻquv)",
                        ),
                    },
                    {
                        "value": "mortgage",
                        "label": l("Ипотека (учебная)", "Ipoteka (oʻquv)"),
                    },
                ],
            )
        ],
        "form",
        [
            rule(
                "correct_product",
                "product",
                "eq",
                "consumer",
                "Выберите потребительский кредит.",
                "Isteʼmol kreditini tanlang.",
            )
        ],
    )
    screen(
        "form",
        "Условия кредита",
        "Kredit shartlari",
        [
            field(
                "amount",
                "number",
                "Сумма, сум",
                "Miqdor, soʻm",
                required=True,
                hint=l(
                    "По заданию: 12 000 000 сум.",
                    "Topshiriq boʻyicha: 12 000 000 soʻm.",
                ),
            ),
            field("months", "number", "Срок, месяцев", "Muddat, oy", required=True),
        ],
        "documents",
        [
            rule(
                "amount_expected",
                "amount",
                "gte",
                12000000,
                "Сумма по заданию: 12 000 000 сум.",
                "Topshiriqdagi miqdor: 12 000 000 soʻm.",
            ),
            rule(
                "amount_limit",
                "amount",
                "lte",
                12000000,
                "Не превышайте сумму задания.",
                "Topshiriq miqdoridan oshmang.",
            ),
            rule(
                "term_expected",
                "months",
                "gte",
                12,
                "Срок по заданию: 12 месяцев.",
                "Topshiriqdagi muddat: 12 oy.",
            ),
            rule(
                "term_limit",
                "months",
                "lte",
                12,
                "Срок по заданию: 12 месяцев.",
                "Topshiriqdagi muddat: 12 oy.",
            ),
        ],
    )
    screen(
        "documents",
        "Проверка документов",
        "Hujjatlarni tekshirish",
        [
            field(
                "document",
                "document",
                "Учебный документ",
                "Oʻquv hujjati",
                required=True,
                options=[
                    {
                        "value": "passport",
                        "label": l(
                            "TRAIN-PASSPORT-001 · Учебный паспорт",
                            "TRAIN-PASSPORT-001 · Oʻquv pasporti",
                        ),
                    },
                    {
                        "value": "expired",
                        "label": l(
                            "TRAIN-EXPIRED · Просроченный документ",
                            "TRAIN-EXPIRED · Muddati tugagan hujjat",
                        ),
                    },
                ],
            ),
            field(
                "verified",
                "checkbox",
                "Документы проверены",
                "Hujjatlar tekshirildi",
                required=True,
            ),
        ],
        "review",
        [
            rule(
                "valid_document",
                "document",
                "eq",
                "passport",
                "Выбран просроченный документ. Нужен действующий учебный паспорт.",
                "Muddati tugagan hujjat tanlandi. Amaldagi oʻquv pasportini tanlang.",
                20,
            )
        ],
    )
    screen(
        "review",
        "Проверка обязательных данных",
        "Majburiy maʼlumotlarni tekshirish",
        [
            field(
                "summary",
                "status",
                "Проверьте введённые данные ниже",
                "Quyidagi maʼlumotlarni tekshiring",
            ),
            field(
                "consent",
                "checkbox",
                "Учебное согласие клиента получено",
                "Mijozning oʻquv roziligi olindi",
                required=True,
            ),
        ],
        "submit",
    )
    screen(
        "submit",
        "Отправка учебной заявки",
        "Oʻquv arizasini yuborish",
        [
            field(
                "submission",
                "modal",
                "Отправляется только виртуальная заявка. Подтвердите действие кнопкой «Продолжить».",
                "Faqat virtual ariza yuboriladi. Davom etish tugmasi bilan tasdiqlang.",
            )
        ],
        "result",
    )
    screen(
        "result",
        "Учебная заявка принята",
        "Oʻquv arizasi qabul qilindi",
        [
            field(
                "accepted",
                "notification",
                "Завершите практику, чтобы получить серверный результат.",
                "Server natijasini olish uchun amaliyotni yakunlang.",
            )
        ],
    )
    tasks = []
    for n, (amount, months) in enumerate(
        [(12000000, 12), (8000000, 6), (15000000, 18)], 1
    ):
        tasks.append(
            {
                "id": f"task_{n}",
                "description": l(
                    f"Оформите для TEST-001 потребительский кредит {amount:,} сум на {months} месяцев. Выберите учебный паспорт и подтвердите проверку документов и согласие.",
                    f"TEST-001 uchun {months} oyga {amount:,} soʻm isteʼmol krediti rasmiylashtiring. Oʻquv pasportini tanlang, hujjatlar tekshiruvi va rozilikni tasdiqlang.",
                ),
                "expected": {"amount": amount, "months": months},
            }
        )
    screens[0]["components"][0]["label"] = l(
        "Выполните индивидуальное задание, указанное над рабочим экраном.",
        "Ish ekrani ustida koʻrsatilgan shaxsiy topshiriqni bajaring.",
    )
    for item in screens:
        for validation in item["rules"]:
            if validation["condition"]["field"] in ("amount", "months"):
                validation["condition"]["task_value"] = True
                validation["message"] = l(
                    "Значение должно соответствовать индивидуальному заданию.",
                    "Qiymat shaxsiy topshiriqqa mos boʻlishi kerak.",
                )
    return Definition.model_validate(
        {
            "tasks": tasks,
            "title": l(
                "Оформление потребительского кредита",
                "Isteʼmol kreditini rasmiylashtirish",
            ),
            "description": l(
                "Учебный банковский процесс на синтетических данных: клиент, заявка, документы и отправка.",
                "Sunʼiy maʼlumotlar asosidagi oʻquv bank jarayoni: mijoz, ariza, hujjatlar va yuborish.",
            ),
            "start": "start",
            "completion": ["result"],
            "screens": screens,
        }
    )
