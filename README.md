# ZettaCode Sales Bot

ZettaCode Tech uchun Telegram savdo agenti. Bot mijozdan loyiha turini tanlatadi, talablarni qabul qiladi, taxminiy narx chiqaradi, 50% karta predoplata bosqichiga o'tkazadi va chekni adminga tekshirtiradi.

Bot narxlar bo'limida quyidagi xizmatlarni ko'rsatadi:

- Telegram botlar: 150$ dan, TWA botlar 300$ dan, kurer/buyurtma botlari 400$ dan;
- Landing page: 200$ dan, korporativ saytlar 400$ dan, online do'konlar 600$ dan;
- Mobil ilovalar: 800$ dan;
- CRM: 350$ dan, hisob-kitob/statistika tizimlari 400$ dan.

## Ishga tushirish

```bash
cd /home/inomjon/zettacode-sales-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` fayliga quyidagilarni yozing:

```env
BOT_TOKEN=telegram_bot_tokeningiz
ADMIN_CHAT_ID=admin_telegram_id
ADMIN_CHAT_IDS=admin_telegram_id,boshqa_admin_id
ADMIN_USERNAME=toshmirzayevinomjon
CARD_NUMBER=karta_raqami
CARD_HOLDER=karta_egasi
GROQ_API_KEY=groq_api_key
GROQ_MODEL=llama-3.1-8b-instant
PROMO_CODES=ZETTA10:10,START5:5
WEB_APP_URL=https://toshmirzayev-inomjon.online/
WEB_APP_BUTTON_TEXT=Web App
REMINDER_AFTER_HOURS=24
WEB_ADMIN_ENABLED=1
WEB_ADMIN_HOST=127.0.0.1
WEB_ADMIN_PORT=8088
WEB_ADMIN_TOKEN=change_this_token
DB_PATH=orders.db
```

Keyin botni ishga tushiring:

```bash
python main.py
```

## Buyruqlar

User commandlar:

- `/start` - botni boshlash
- `/new` - yangi buyurtma boshlash
- `/prices` - xizmatlar narxlarini ko'rish
- `/portfolio` - portfolio havolasi
- `/contact` - admin bilan aloqa
- `/status` - mijozning oxirgi buyurtma holati
- `/invoice` - mijozning oxirgi buyurtmasi uchun invoice PDF
- `/faq` - ko'p beriladigan savollar
- `/promo PROMOKOD` - promo kod kiritish
- `/help` - yordam
- `/cancel` - joriy buyurtmani bekor qilish

Admin commandlar:

- `/admin` - admin panel
- `/orders` - oxirgi buyurtmalar, `/orders paid` kabi status filter ham ishlaydi
- `/stats` - buyurtmalar statistikasi
- `/ai` - AI ulanish holati
- `/testorder` - mijoz sifatida test buyurtma
- `/search matn` - buyurtma ID, user ID, username yoki talab matni bo'yicha qidirish
- `/note BUYURTMA_ID izoh` - buyurtmaga ichki admin izoh qo'shish
- `/draft BUYURTMA_ID` - AI texnik topshiriq drafti
- `/invoice BUYURTMA_ID` - invoice PDF olish
- `/stage BUYURTMA_ID BOSQICH` - CRM pipeline bosqichini o'zgartirish
- `/task BUYURTMA_ID matn` - buyurtmaga vazifa qo'shish
- `/tasks BUYURTMA_ID` - buyurtma vazifalarini ko'rish
- `/done TASK_ID` - vazifani bajarildi qilish
- `/deadline BUYURTMA_ID YYYY-MM-DD` - deadline qo'yish
- `/assign BUYURTMA_ID ism` - mas'ul admin/xodim biriktirish
- `/web` - web admin panel havolasi
- `/export` - buyurtmalarni CSV fayl qilib olish
- `/broadcast matn` - barcha mijozlarga xabar yuborish
- `/block USER_ID sabab` - foydalanuvchini bloklash
- `/unblock USER_ID` - blokdan chiqarish
- `/backup` - database backup faylini olish

## Tugmalar

Bot inline tugmalar va pastki reply klaviatura bilan ishlaydi:

- `Buyurtma berish` - yangi buyurtma boshlaydi;
- `Narxlar` - minimal narxlarni ko'rsatadi;
- `Narxni hisoblash` - yig'ilgan talablar asosida AI baholashni boshlaydi;
- `Bekor qilish` - joriy buyurtmani bekor qiladi;
- `Admin panel` - faqat admin uchun panelni ochadi.

## Oqim

1. Mijoz `Telegram bot`, `Veb-sayt`, `Mobil ilova`, `CRM / hisob-kitob tizimi` yo'nalishlaridan bir yoki bir nechtasini tanlaydi yoki loyiha haqida erkin matn yozadi.
2. Bot Groq AI orqali matn loyiha buyurtmasiga tegishlimi yoki yo'qligini tekshiradi.
3. Mavzudan tashqari xabarlar muloyim tarzda rad qilinadi va mijoz loyiha talablariga qaytariladi.
4. Mijoz juda oz ma'lumot yozsa, bot narx chiqarmaydi va `Bu ma'lumot kam. Bu bilan sizning loyihangizni qila olmaymiz.` deb aniqlashtiruvchi savollar beradi.
5. Bot talablarni bosqichma-bosqich yig'adi. Loyiha nima qilishi, asosiy funksiyalar va foydalanuvchi/admin amallari tushunarli bo'lgandan keyingina qabul qiladi.
6. Bot Groq AI orqali talablarni tahlil qiladi. AI ishlamasa, minimal narxlar va kalit so'zlar bo'yicha fallback hisob-kitob ishlaydi.
7. Bot ZettaCode xizmatini boshlash uchun 50% predoplatani karta orqali so'raydi.
8. Agar mijoz oldindan predoplata qilishni istamasa, bot buyurtmani `Admin bilan kelishish kerak` statusiga o'tkazadi va `ADMIN_USERNAME` dagi admin lichkasini beradi.
9. Mijoz chek rasmini yuborsa, buyurtma va chek ma'lumotlari adminga boradi.
10. Admin karta to'lovi tushganini tekshiradi.
11. Admin `PUL TUSHDI (Ha)` yoki `PUL TUSHMADI (Yo'q)` tugmasini bosadi.
12. Bot mijozga ssenariy bo'yicha yakuniy javobni yuboradi.

Loyiha ichidagi to'lov cheklovi: mijoz buyurtma qilayotgan bot/sayt/ilova/CRM ichida Click, Payme, Paynet, karta yoki boshqa online to'lov integratsiyasi qabul qilinmaydi. Bunday funksiyalar faqat naqd to'lov sifatida ko'rib chiqiladi.

## Admin panel

Admin ID `.env` dagi `ADMIN_CHAT_ID` yoki `ADMIN_CHAT_IDS` ichida bo'lsa, `/start` oddiy mijoz oqimini ochmaydi. Admin panelda:

- web admin panelni ochish;
- CRM pipeline bosqichlarini boshqarish;
- oxirgi buyurtmalarni ko'rish;
- status bo'yicha filterlash;
- buyurtma qidirish;
- buyurtmaga ichki izoh yozish;
- buyurtmaga vazifa, deadline va mas'ul qo'yish;
- buyurtma tafsilotini ochish;
- to'lovni tasdiqlash yoki rad etish;
- texnik topshiriq draftini olish;
- invoice PDF yaratish;
- CSV export va database backup olish;
- broadcast yuborish;
- userlarni bloklash yoki blokdan chiqarish;
- statistikani ko'rish;
- AI ulanish holatini tekshirish;
- mijoz sifatida test buyurtma qilish mumkin.

## Qo'shimcha funksiyalar

- Telegram pastki `Menu` tugmasi `WEB_APP_URL` dagi Web Appni ochadi. URL HTTPS bo'lishi shart.
- CRM pipeline: `new`, `requirements`, `priced`, `prepayment`, `in_progress`, `done`.
- Avtomatik eslatma: narx olgan, chek yubormagan yoki admin bilan kelishishga o'tgan mijozlarga `REMINDER_AFTER_HOURS` soatdan keyin xabar yuboriladi.
- AI va fallback baholash: narx bilan birga taxminiy muddat va lead score chiqadi.
- PDF invoice: admin yoki mijoz buyurtma bo'yicha PDF invoice olishi mumkin.
- Ichki portfolio katalog: bot ichida Telegram bot, veb-sayt, CRM va mobil ilova yo'nalishlari bo'yicha keyslar ko'rsatiladi.
- Web admin panel: `WEB_ADMIN_HOST:WEB_ADMIN_PORT` orqali brauzerda buyurtmalar va statistikani ko'rish mumkin.

## Xavfsizlik va deploy

- `.env`, `orders.db`, `bot.log`, `.venv` va `backups/` GitHubga chiqmaydi.
- Bot spam xabarlarni rate-limit qiladi.
- `zettacode-bot.service.example` fayli systemd orqali doimiy ishga tushirish namunasi sifatida qo'shilgan.
- `zettacode-bot.logrotate.example` log faylni aylantirish uchun namuna.
- `scripts/backup_db.sh` database backup oladi.
- `scripts/deploy_restart.sh` kodni yangilab, service restart qilish uchun namuna.
