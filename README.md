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
ADMIN_USERNAME=toshmirzayevinomjon
CARD_NUMBER=karta_raqami
CARD_HOLDER=karta_egasi
GROQ_API_KEY=groq_api_key
GROQ_MODEL=llama-3.1-8b-instant
DB_PATH=orders.db
```

Keyin botni ishga tushiring:

```bash
python main.py
```

## Buyruqlar

- `/start` - botni boshlash
- `/new` - yangi buyurtma boshlash
- `/admin` - admin panel

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

Admin ID `.env` dagi `ADMIN_CHAT_ID` bilan bir xil bo'lsa, `/start` oddiy mijoz oqimini ochmaydi. Admin panelda:

- oxirgi buyurtmalarni ko'rish;
- buyurtma tafsilotini ochish;
- to'lovni tasdiqlash yoki rad etish;
- statistikani ko'rish;
- AI ulanish holatini tekshirish;
- mijoz sifatida test buyurtma qilish mumkin.
