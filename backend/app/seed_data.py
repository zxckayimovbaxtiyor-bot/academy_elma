"""Reference data and synthetic demo data. No real client or employee data anywhere.

Regions are public geography. Branches, people and the demo wave are invented;
real branches are loaded with ``cli import-branches``.
"""

from __future__ import annotations

COURSE = {"code": "single-window", "title_uz": "Yagona oyna", "title_ru": "Единое окно"}

# code, name_uz, name_ru
REGIONS = [
    ("01", "Toshkent shahri", "город Ташкент"),
    ("02", "Toshkent viloyati", "Ташкентская область"),
    ("03", "Andijon viloyati", "Андижанская область"),
    ("04", "Buxoro viloyati", "Бухарская область"),
    ("05", "Fargʻona viloyati", "Ферганская область"),
    ("06", "Jizzax viloyati", "Джизакская область"),
    ("07", "Xorazm viloyati", "Хорезмская область"),
    ("08", "Namangan viloyati", "Наманганская область"),
    ("09", "Navoiy viloyati", "Навоийская область"),
    ("10", "Qashqadaryo viloyati", "Кашкадарьинская область"),
    ("11", "Samarqand viloyati", "Самаркандская область"),
    ("12", "Sirdaryo viloyati", "Сырдарьинская область"),
    ("13", "Surxondaryo viloyati", "Сурхандарьинская область"),
    ("14", "Qoraqalpogʻiston Respublikasi", "Республика Каракалпакстан"),
]

# code, name_uz, name_ru, sort, is_branch_head
JOB_ROLES = [
    ("menejer", "Menejer", "Менеджер", 1, False),
    ("korporativ_menejer", "Korporativ menejer", "Корпоративный менеджер", 2, False),
    ("anderrayter", "Anderrayter", "Андеррайтер", 3, False),
    ("operatsion_xodim", "Operatsion xodim", "Операционный сотрудник", 4, False),
    ("filial_rahbari", "Filial rahbari", "Руководитель филиала", 5, True),
]

# code, qprefix, type, title_uz, title_ru  (spec seed list; admin can rename/reorder)
MODULES = [
    ("CORE", "A", "core", "Asosiy: Yagona oyna bilan ishlash", "Основной: работа в Едином окне"),
    ("FAROVON", "F", "product", "Farovon ipoteka", "Ипотека «Фаровон»"),
    ("RETAIL", "CK", "product", "Chakana kredit konveyeri", "Розничный кредитный конвейер"),
    ("UZCARD", "U", "product", "Uzcard karta chiqarish", "Выпуск карт Uzcard"),
    (
        "LEGAL",
        "YK",
        "product",
        "Yuridik shaxslar kredit konveyeri",
        "Кредитный конвейер для юридических лиц",
    ),
    ("CRM", "CRM", "product", "CRM asoslari", "Основы CRM"),
    ("FAQ", "FAQ", "faq", "Koʻp beriladigan savollar", "Часто задаваемые вопросы"),
]

# --- synthetic only ---------------------------------------------------------------

# Tashkent city districts → branch "<district> BXM" (bank xizmatlari markazi).
TASHKENT_DISTRICTS = [
    ("Bektemir", "Бектемир"),
    ("Chilonzor", "Чиланзар"),
    ("Mirobod", "Мирабад"),
    ("Mirzo Ulugʻbek", "Мирзо-Улугбек"),
    ("Olmazor", "Алмазар"),
    ("Sergeli", "Сергели"),
    ("Shayxontohur", "Шайхантахур"),
    ("Uchtepa", "Учтепа"),
    ("Yakkasaroy", "Яккасарай"),
    ("Yashnobod", "Яшнабад"),
    ("Yunusobod", "Юнусабад"),
    ("Yangihayot", "Янгихаёт"),
]

# One branch per other region: region code, city uz, city ru.
REGIONAL_CITIES = [
    ("02", "Nurafshon", "Нурафшан"),
    ("03", "Andijon", "Андижан"),
    ("04", "Buxoro", "Бухара"),
    ("05", "Fargʻona", "Фергана"),
    ("06", "Jizzax", "Джизак"),
    ("07", "Urganch", "Ургенч"),
    ("08", "Namangan", "Наманган"),
    ("09", "Navoiy", "Навои"),
    ("10", "Qarshi", "Карши"),
    ("11", "Samarqand", "Самарканд"),
    ("12", "Guliston", "Гулистан"),
    ("13", "Termiz", "Термез"),
    ("14", "Nukus", "Нукус"),
]

TASHKENT_BRANCH_STAFF = (
    ["filial_rahbari", "anderrayter", "korporativ_menejer", "operatsion_xodim"] + ["menejer"] * 11
)
REGIONAL_BRANCH_STAFF = ["filial_rahbari", "anderrayter", "operatsion_xodim", "menejer", "menejer"]

MALE_NAMES = [
    "Akmal", "Bekzod", "Jasur", "Sardor", "Timur", "Otabek", "Rustam", "Shoxrux",
    "Doniyor", "Aziz", "Javohir", "Sherzod", "Ulugʻbek", "Farrux", "Bobur",
]  # fmt: skip
FEMALE_NAMES = [
    "Dilnoza", "Malika", "Nodira", "Gulnora", "Madina", "Zarina", "Shahnoza", "Feruza",
    "Kamola", "Nilufar", "Sevara", "Dildora", "Mohira", "Barno", "Laylo",
]  # fmt: skip
SURNAMES = [
    "Rahimov", "Tursunov", "Qodirov", "Ergashev", "Abdullayev", "Xasanov", "Karimov",
    "Yusupov", "Saidov", "Aliyev", "Toshmatov", "Nazarov", "Mirzayev", "Umarov", "Ismoilov",
]  # fmt: skip
RU_MALE_NAMES = ["Sergey", "Dmitriy", "Aleksandr", "Andrey", "Vladimir"]
RU_FEMALE_NAMES = ["Elena", "Olga", "Irina", "Natalya", "Svetlana"]
RU_SURNAMES = ["Kim", "Pak", "Ten", "Li", "Tsoy"]  # same form for both genders

DEMO_WAVE = {
    "name_uz": "1-toʻlqin · Toshkent shahri",
    "name_ru": "1-я волна · город Ташкент",
    "training_start_offset_days": -14,
    "deadline_offset_days": 30,
    "go_live_offset_days": 45,
}
# Role x module matrix of the demo wave (Core is implicit), as in mockup 9.
DEMO_ASSIGNMENTS = {
    "menejer": ["FAROVON", "RETAIL", "UZCARD", "CRM"],
    "korporativ_menejer": ["LEGAL", "CRM"],
    "anderrayter": ["FAROVON", "RETAIL", "LEGAL"],
    "operatsion_xodim": ["UZCARD", "CRM"],
    "filial_rahbari": ["FAROVON", "RETAIL", "UZCARD", "LEGAL", "CRM"],
}

# Demo learning path (`seed --demo`): a wave whose menejer takes Core + Farovon only, so one
# sitting covers fail → re-watch → pass → product → module and operator certificates.
DEMO_PATH = {
    "wave_uz": "Demo toʻlqini · Asosiy + Farovon",
    "wave_ru": "Демо-волна · Основной + Фаровон",
    "branch_code": "01-900",
    "branch_uz": "Demo BXM",
    "branch_ru": "Демо ЦБУ",
    "region_code": "01",
    "job_role": "menejer",
    "products": ["FAROVON"],
    "employee_id": "DEMO-0001",
    "full_name": "Demo Oʻquvchi",
}

# Demo content (`seed --demo`): short generated test-pattern videos, published as one release.
DEMO_RELEASE_CODE = "2026.11"
DEMO_VIDEO_SECONDS = 40
DEMO_LESSONS = {
    "CORE": [
        ("Kirish", "Введение"),
        ("Mijozni qidirish", "Поиск клиента"),
        ("Mijoz kartasi", "Карточка клиента"),
    ],
    "FAROVON": [
        ("Mahsulot va shartlar", "Продукт и условия"),
        ("Arizani yaratish", "Создание заявки"),
    ],
}
