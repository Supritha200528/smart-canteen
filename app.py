"""Smart Canteen Ordering System - Flask + SQLite backend (REST API + static SPA)."""
import os
import re
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, Response, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

from qr_generator import generate_qr_svg

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'student'
);

CREATE TABLE IF NOT EXISTS menu_items(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  description TEXT DEFAULT '',
  price INTEGER NOT NULL CHECK(price >= 0),
  stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
  available INTEGER NOT NULL DEFAULT 1,
  image TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  token INTEGER NOT NULL,
  order_date TEXT NOT NULL,
  slot TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'placed',
  total INTEGER NOT NULL,
  payment_method TEXT NOT NULL DEFAULT 'counter',
  payment_status TEXT NOT NULL DEFAULT 'unpaid',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items(
  id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES orders(id),
  item_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  price INTEGER NOT NULL,
  qty INTEGER NOT NULL
);
"""

# Realistic Indian Canteen Menu Items (Breakfast, Lunch, Snacks, Fast Food, Beverages)
# Exact authentic image mapping for every food item - no shared or unrelated images
FOOD_IMAGE_MAP = {
    # Breakfast
    "masala dosa": "https://images.unsplash.com/photo-1668236543090-82eba5ee5976?auto=format&fit=crop&w=600&h=400&q=80",
    "idli vada (2+1)": "https://images.unsplash.com/photo-1589301760014-d929f3979dbc?auto=format&fit=crop&w=600&h=400&q=80",
    "idli vada combo (2+1)": "https://images.unsplash.com/photo-1589301760014-d929f3979dbc?auto=format&fit=crop&w=600&h=400&q=80",
    "plain dosa": "https://images.unsplash.com/photo-1694665424564-924a3501a37c?auto=format&fit=crop&w=600&h=400&q=80",
    "mysore masala dosa": "https://images.unsplash.com/photo-1626777552726-4a6b54c97e46?auto=format&fit=crop&w=600&h=400&q=80",
    "pongal": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f5/Ven_Pongal.jpg/640px-Ven_Pongal.jpg",
    "ghee pongal": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f5/Ven_Pongal.jpg/640px-Ven_Pongal.jpg",
    "puri bhaji (3 pcs)": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Poori_Bhaji_served_in_a_Plate.jpg/640px-Poori_Bhaji_served_in_a_Plate.jpg",
    "aloo paratha (2 pcs)": "https://images.unsplash.com/photo-1626074353765-517a681e40be?auto=format&fit=crop&w=600&h=400&q=80",
    "rava upma": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ae/Upma%2C_popular_breakfast_item_in_India.jpg/640px-Upma%2C_popular_breakfast_item_in_India.jpg",
    "kanda poha": "https://images.unsplash.com/photo-1645177628172-a94c1f96e6db?auto=format&fit=crop&w=600&h=400&q=80",
    "medu vada (2 pcs)": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Medu_vada.jpg/640px-Medu_vada.jpg",

    # Lunch
    "south indian veg meals": "https://images.unsplash.com/photo-1610192244261-3f33de3f55e4?auto=format&fit=crop&w=600&h=400&q=80",
    "veg meals": "https://images.unsplash.com/photo-1610192244261-3f33de3f55e4?auto=format&fit=crop&w=600&h=400&q=80",
    "north indian executive thali": "https://images.unsplash.com/photo-1546833999-b9f581a1996d?auto=format&fit=crop&w=600&h=400&q=80",
    "veg dum biryani": "https://images.unsplash.com/photo-1563379091339-03b21ab4a4f8?auto=format&fit=crop&w=600&h=400&q=80",
    "veg biryani": "https://images.unsplash.com/photo-1563379091339-03b21ab4a4f8?auto=format&fit=crop&w=600&h=400&q=80",
    "paneer butter masala with rotis": "https://images.unsplash.com/photo-1631452180519-c014fe946bc7?auto=format&fit=crop&w=600&h=400&q=80",
    "dal tadka with jeera rice": "https://images.unsplash.com/photo-1585937421612-70a008356fbe?auto=format&fit=crop&w=600&h=400&q=80",
    "rajma chawal bowl": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/Rajma_Chawal_with_onion_rings_and_chilli.jpg/640px-Rajma_Chawal_with_onion_rings_and_chilli.jpg",
    "chole bhature (2 pcs)": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Chole_Bhature_at_Bengali_Sweet_Centre%2C_South_Extension%2C_New_Delhi.jpg/640px-Chole_Bhature_at_Bengali_Sweet_Centre%2C_South_Extension%2C_New_Delhi.jpg",
    "curd rice with pickle": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cf/Curd_Rice_Thali.jpg/640px-Curd_Rice_Thali.jpg",
    "curd rice": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cf/Curd_Rice_Thali.jpg/640px-Curd_Rice_Thali.jpg",
    "lemon rice with papad": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/Chitranna_Lemon_Rice.jpg/640px-Chitranna_Lemon_Rice.jpg",
    "veg pulao with raita": "https://images.unsplash.com/photo-1512058564366-18510be2db19?auto=format&fit=crop&w=600&h=400&q=80",

    # Snacks
    "samosa (2 pcs)": "https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=600&h=400&q=80",
    "veg puff": "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=600&h=400&q=80",
    "pav bhaji": "https://images.unsplash.com/photo-1606491956689-2ea866880c84?auto=format&fit=crop&w=600&h=400&q=80",
    "vada pav (2 pcs)": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Vada_Pav-Indian_street_food.JPG/640px-Vada_Pav-Indian_street_food.JPG",
    "crispy onion pakoda": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/88/Onion_pakoda.jpg/640px-Onion_pakoda.jpg",
    "paneer pakoda (4 pcs)": "https://images.unsplash.com/photo-1565557623262-b51c2513a641?auto=format&fit=crop&w=600&h=400&q=80",
    "bhel puri": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/82/Bhel_Puri_Chaat.JPG/640px-Bhel_Puri_Chaat.JPG",
    "sev puri": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/52/Sev_Batata_Puri.jpg/640px-Sev_Batata_Puri.jpg",
    "bread pakoda": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7f/Bread_Pakora_served_with_chutney.jpg/640px-Bread_Pakora_served_with_chutney.jpg",
    "mirchi bajji (3 pcs)": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/07/Mirchi_bajji.jpg/640px-Mirchi_bajji.jpg",
    "gobi": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ad/Gobi_Manchurian.jpg/640px-Gobi_Manchurian.jpg",

    # Fast Food
    "veg cheese grilled sandwich": "https://images.unsplash.com/photo-1528735602780-2552fd46c7af?auto=format&fit=crop&w=600&h=400&q=80",
    "crispy veg burger": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=600&h=400&q=80",
    "veg hakka noodles": "https://images.unsplash.com/photo-1585032226651-759b368d7246?auto=format&fit=crop&w=600&h=400&q=80",
    "veg fried rice": "https://images.unsplash.com/photo-1603133872878-684f208fb84b?auto=format&fit=crop&w=600&h=400&q=80",
    "paneer kathi roll": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cb/Paneer_Tikka_Kathi_Roll.jpg/640px-Paneer_Tikka_Kathi_Roll.jpg",
    "peri peri french fries": "https://images.unsplash.com/photo-1576107232684-1279f3908594?auto=format&fit=crop&w=600&h=400&q=80",
    "chilli paneer (dry)": "https://images.unsplash.com/photo-1567188040759-fb8a883dc6d8?auto=format&fit=crop&w=600&h=400&q=80",
    "veg spring rolls (4 pcs)": "https://images.unsplash.com/photo-1544025162-d76694265947?auto=format&fit=crop&w=600&h=400&q=80",

    # Beverages
    "filter coffee": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?auto=format&fit=crop&w=600&h=400&q=80",
    "masala chai": "https://images.unsplash.com/photo-1576092768241-dec231879fc3?auto=format&fit=crop&w=600&h=400&q=80",
    "chilled masala buttermilk": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Chaas_Buttermilk.jpg/640px-Chaas_Buttermilk.jpg",
    "buttermilk": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Chaas_Buttermilk.jpg/640px-Chaas_Buttermilk.jpg",
    "sweet punjabi lassi": "https://images.unsplash.com/photo-1553530666-ba11a7da3888?auto=format&fit=crop&w=600&h=400&q=80",
    "fresh lime soda": "https://images.unsplash.com/photo-1513558161293-cdaf765ed2fd?auto=format&fit=crop&w=600&h=400&q=80",
    "cold coffee with ice cream": "https://images.unsplash.com/photo-1517701550927-30cf4ba1dba5?auto=format&fit=crop&w=600&h=400&q=80",
    "mango lassi": "https://images.unsplash.com/photo-1546173159-315724a31696?auto=format&fit=crop&w=600&h=400&q=80",
    "badam milk (hot / cold)": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/22/Badam_Milk.jpg/640px-Badam_Milk.jpg",
}

SEED_MENU = [
    # Breakfast
    ("Masala Dosa", "Breakfast", "Crispy golden crepe filled with spiced potato masala, served with coconut chutney & sambar", 50, 45, 1, FOOD_IMAGE_MAP["masala dosa"]),
    ("Idli Vada Combo (2+1)", "Breakfast", "Steamed fluffy rice cakes paired with a crunchy medu vada, fresh coconut chutney & hot sambar", 45, 50, 1, FOOD_IMAGE_MAP["idli vada combo (2+1)"]),
    ("Plain Dosa", "Breakfast", "Classic crisp fermented rice crepe served hot with aromatic sambar and mint-coconut chutney", 40, 40, 1, FOOD_IMAGE_MAP["plain dosa"]),
    ("Mysore Masala Dosa", "Breakfast", "Crispy dosa layered with spicy red garlic chutney and spiced potato mash, served with sambar", 60, 35, 1, FOOD_IMAGE_MAP["mysore masala dosa"]),
    ("Ghee Pongal", "Breakfast", "Rich comforting rice and yellow lentil dish tempered with roasted cumin, black pepper, ginger & cashews", 40, 30, 1, FOOD_IMAGE_MAP["ghee pongal"]),
    ("Puri Bhaji (3 pcs)", "Breakfast", "Puffed golden whole wheat puris served with flavourful spiced potato masala bhaji", 50, 35, 1, FOOD_IMAGE_MAP["puri bhaji (3 pcs)"]),
    ("Aloo Paratha (2 pcs)", "Breakfast", "Whole wheat griddled flatbread stuffed with spiced mashed potatoes, served with butter & curd", 60, 30, 1, FOOD_IMAGE_MAP["aloo paratha (2 pcs)"]),
    ("Rava Upma", "Breakfast", "Savory roasted semolina porridge tempered with mustard seeds, curry leaves, veggies & crunchy peanuts", 30, 25, 1, FOOD_IMAGE_MAP["rava upma"]),
    ("Kanda Poha", "Breakfast", "Flattened rice flakes sautéed with turmeric, crunchy peanuts, mustard seeds, onions & fresh coriander", 30, 30, 1, FOOD_IMAGE_MAP["kanda poha"]),
    ("Medu Vada (2 pcs)", "Breakfast", "Crispy deep-fried lentil donuts with a soft fluffy interior, served with coconut chutney & sambar", 35, 40, 1, FOOD_IMAGE_MAP["medu vada (2 pcs)"]),

    # Lunch
    ("South Indian Veg Meals", "Lunch", "Steamed rice, sambar, rasam, kootu, veg poriyal, curd, papad, pickle & sweet kesari", 80, 50, 1, FOOD_IMAGE_MAP["south indian veg meals"]),
    ("North Indian Executive Thali", "Lunch", "2 Phulkas, Paneer butter masala, Dal makhani, Jeera rice, Gulab jamun & salad", 95, 45, 1, FOOD_IMAGE_MAP["north indian executive thali"]),
    ("Veg Dum Biryani", "Lunch", "Fragrant basmati rice layered with spiced vegetables, saffron, fried onions, served with mint raita", 85, 40, 1, FOOD_IMAGE_MAP["veg dum biryani"]),
    ("Paneer Butter Masala with Rotis", "Lunch", "Cottage cheese cubes simmered in a creamy tomato-cashew gravy with fresh soft rotis", 85, 35, 1, FOOD_IMAGE_MAP["paneer butter masala with rotis"]),
    ("Dal Tadka with Jeera Rice", "Lunch", "Yellow toor dal tempered with ghee, cumin, garlic, and red chilies paired with cumin basmati rice", 70, 40, 1, FOOD_IMAGE_MAP["dal tadka with jeera rice"]),
    ("Rajma Chawal Bowl", "Lunch", "Hearty red kidney beans slow-cooked in a rich spiced Punjabi gravy served over steamed rice", 70, 35, 1, FOOD_IMAGE_MAP["rajma chawal bowl"]),
    ("Chole Bhature (2 pcs)", "Lunch", "Fluffy deep-fried leavened bread served with tangy, spicy chickpea curry, pickled onions & green chilli", 75, 40, 1, FOOD_IMAGE_MAP["chole bhature (2 pcs)"]),
    ("Curd Rice with Pickle", "Lunch", "Creamy seasoned yogurt rice tempered with mustard, curry leaves, ginger, pomegranate & lemon pickle", 40, 40, 1, FOOD_IMAGE_MAP["curd rice with pickle"]),
    ("Lemon Rice with Papad", "Lunch", "Zesty basmati rice infused with lemon juice, turmeric, curry leaves, and crunchy roasted peanuts", 45, 35, 1, FOOD_IMAGE_MAP["lemon rice with papad"]),
    ("Veg Pulao with Raita", "Lunch", "Mildly spiced fragrant long-grain rice with garden-fresh vegetables and roasted cumin curd", 70, 30, 1, FOOD_IMAGE_MAP["veg pulao with raita"]),

    # Snacks
    ("Samosa (2 pcs)", "Snacks", "Crispy triangular pastry pockets packed with spiced potato and green peas, served with mint & tamarind chutney", 25, 60, 1, FOOD_IMAGE_MAP["samosa (2 pcs)"]),
    ("Veg Puff", "Snacks", "Flaky golden bakery puff stuffed with spiced potato, carrots and sweet green peas", 20, 50, 1, FOOD_IMAGE_MAP["veg puff"]),
    ("Pav Bhaji", "Snacks", "Spiced mashed vegetable curry cooked on a tawa with butter, served with two soft butter-toasted pav buns", 70, 40, 1, FOOD_IMAGE_MAP["pav bhaji"]),
    ("Vada Pav (2 pcs)", "Snacks", "Mumbai-style spiced potato fritter batata vada in pav bread smeared with garlic chutney and fried green chillies", 35, 55, 1, FOOD_IMAGE_MAP["vada pav (2 pcs)"]),
    ("Crispy Onion Pakoda", "Snacks", "Crunchy golden sliced onion fritters seasoned with carom seeds, ginger, and curry leaves", 30, 45, 1, FOOD_IMAGE_MAP["crispy onion pakoda"]),
    ("Paneer Pakoda (4 pcs)", "Snacks", "Thick cottage cheese slices coated in seasoned gram flour batter, fried crisp and sprinkled with chaat masala", 50, 35, 1, FOOD_IMAGE_MAP["paneer pakoda (4 pcs)"]),
    ("Bhel Puri", "Snacks", "Puffed rice tossed with chopped onions, tomatoes, sev, crisp puris, spicy green chutney and sweet date chutney", 35, 40, 1, FOOD_IMAGE_MAP["bhel puri"]),
    ("Sev Puri", "Snacks", "Crisp flat puris topped with potato dice, chopped onions, trio of chutneys and mountain of golden sev", 40, 35, 1, FOOD_IMAGE_MAP["sev puri"]),
    ("Bread Pakoda", "Snacks", "Triangular bread sandwich filled with spiced potato masala, dipped in besan batter and fried golden", 25, 40, 1, FOOD_IMAGE_MAP["bread pakoda"]),
    ("Mirchi Bajji (3 pcs)", "Snacks", "Large mild green chillies stuffed with spices, dipped in gram flour batter and fried until crunchy", 30, 35, 1, FOOD_IMAGE_MAP["mirchi bajji (3 pcs)"]),

    # Fast Food
    ("Veg Cheese Grilled Sandwich", "Fast Food", "Double-layered sandwich loaded with spiced vegetable slices, mint chutney, and molten melted cheese", 55, 35, 1, FOOD_IMAGE_MAP["veg cheese grilled sandwich"]),
    ("Crispy Veg Burger", "Fast Food", "Crispy seasoned vegetable patty with crisp lettuce, onion rings, tomatoes & creamy burger mayo", 60, 30, 1, FOOD_IMAGE_MAP["crispy veg burger"]),
    ("Veg Hakka Noodles", "Fast Food", "Wok-tossed stir-fried noodles with crunchy cabbage, bell peppers, carrots, spring onions and soy sauce", 65, 40, 1, FOOD_IMAGE_MAP["veg hakka noodles"]),
    ("Veg Fried Rice", "Fast Food", "Aromatic basmati rice tossed on high flame with diced seasonal veggies, garlic and light soy sauce", 65, 40, 1, FOOD_IMAGE_MAP["veg fried rice"]),
    ("Paneer Kathi Roll", "Fast Food", "Tawa-grilled spiced paneer cubes, pickled onions, and mint mayo wrapped in a warm whole-wheat paratha", 70, 35, 1, FOOD_IMAGE_MAP["paneer kathi roll"]),
    ("Peri Peri French Fries", "Fast Food", "Crispy deep-fried golden potato fingers tossed in spicy, tangy peri-peri seasoning", 45, 45, 1, FOOD_IMAGE_MAP["peri peri french fries"]),
    ("Chilli Paneer (Dry)", "Fast Food", "Battered paneer cubes wok-tossed with green bell peppers, onions, green chillies & spicy Indo-Chinese sauce", 80, 30, 1, FOOD_IMAGE_MAP["chilli paneer (dry)"]),
    ("Veg Spring Rolls (4 pcs)", "Fast Food", "Crispy rolls filled with shredded stir-fried cabbage, carrots, bell peppers, served with sweet chilli dip", 50, 35, 1, FOOD_IMAGE_MAP["veg spring rolls (4 pcs)"]),

    # Beverages
    ("Filter Coffee", "Beverages", "Authentic South Indian chicory-blend decoction coffee frothed with hot creamy milk", 15, 100, 1, FOOD_IMAGE_MAP["filter coffee"]),
    ("Masala Chai", "Beverages", "Brewed black tea infused with fresh crushed ginger, cardamom, cinnamon and creamy milk", 15, 100, 1, FOOD_IMAGE_MAP["masala chai"]),
    ("Chilled Masala Buttermilk", "Beverages", "Cooling churned curd infused with crushed green chilies, ginger, toasted cumin and fresh coriander", 20, 60, 1, FOOD_IMAGE_MAP["chilled masala buttermilk"]),
    ("Sweet Punjabi Lassi", "Beverages", "Thick creamy chilled yogurt churned with sugar, fragrant cardamom and topped with malai", 35, 40, 1, FOOD_IMAGE_MAP["sweet punjabi lassi"]),
    ("Fresh Lime Soda", "Beverages", "Refreshing fizzy soda with freshly squeezed lime juice, mint leaves, and sweet or salted syrup", 25, 50, 1, FOOD_IMAGE_MAP["fresh lime soda"]),
    ("Cold Coffee with Ice Cream", "Beverages", "Chilled blended espresso with cold milk, chocolate drizzle and a scoop of vanilla cream", 45, 40, 1, FOOD_IMAGE_MAP["cold coffee with ice cream"]),
    ("Mango Lassi", "Beverages", "Thick velvety drink blending Alphonso mango pulp, creamy yogurt, and a pinch of saffron", 45, 35, 1, FOOD_IMAGE_MAP["mango lassi"]),
    ("Badam Milk (Hot / Cold)", "Beverages", "Rich milk flavored with almond paste, saffron strands, and crushed pistachios", 30, 40, 1, FOOD_IMAGE_MAP["badam milk (hot / cold)"]),
]

# Order status workflow state-machine
# Supports both original flow and new comprehensive status updates:
# Pending (placed) -> Accepted -> Preparing -> Ready -> Completed (collected)
FLOW = {
    "placed": ["accepted", "preparing", "cancelled"],
    "accepted": ["preparing", "cancelled"],
    "preparing": ["ready", "cancelled"],
    "ready": ["completed", "collected"],
    "completed": [],
    "collected": [],
    "cancelled": [],
}

SLOT_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def create_app(config=None):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DB_PATH=os.environ.get("DB_PATH", "canteen.db"),
        SLOT_CAPACITY=int(os.environ.get("SLOT_CAPACITY", "8")),
        STAFF_EMAIL=os.environ.get("STAFF_EMAIL", "staff@canteen.local"),
        STAFF_PASSWORD=os.environ.get("STAFF_PASSWORD", "staff123"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if config:
        app.config.update(config)

    def db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DB_PATH"], isolation_level=None)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys=ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_):
        conn = g.pop("db", None)
        if conn:
            conn.close()

    with app.app_context():
        conn = db()
        conn.executescript(SCHEMA)

        # Migrations for existing databases
        m_cols = [r["name"] for r in conn.execute("PRAGMA table_info(menu_items)").fetchall()]
        if "image" not in m_cols:
            conn.execute("ALTER TABLE menu_items ADD COLUMN image TEXT DEFAULT ''")

        o_cols = [r["name"] for r in conn.execute("PRAGMA table_info(orders)").fetchall()]
        if "payment_method" not in o_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'counter'")
        if "payment_status" not in o_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'unpaid'")

        # Seed staff user
        if not conn.execute("SELECT 1 FROM users WHERE role='staff'").fetchone():
            conn.execute(
                "INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'staff')",
                ("Canteen Staff", app.config["STAFF_EMAIL"],
                 generate_password_hash(app.config["STAFF_PASSWORD"]))
            )

        # Seed or enrich menu items
        existing_count = conn.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
        if existing_count < 35:
            # Map legacy 'Drinks' to 'Beverages' if present
            conn.execute("UPDATE menu_items SET category='Beverages' WHERE category='Drinks'")
            existing_names = {r["name"].lower() for r in conn.execute("SELECT name FROM menu_items").fetchall()}
            for item in SEED_MENU:
                name, category, desc, price, stock, avail, img = item
                if name.lower() not in existing_names:
                    conn.execute(
                        "INSERT INTO menu_items(name,category,description,price,stock,available,image) VALUES(?,?,?,?,?,?,?)",
                        (name, category, desc, price, stock, avail, img)
                    )

        # Synchronize accurate authentic food images for all existing menu items
        for food_name, img_url in FOOD_IMAGE_MAP.items():
            conn.execute(
                "UPDATE menu_items SET image=? WHERE LOWER(name)=?",
                (img_url, food_name.lower())
            )

    def fail(msg, code=400):
        return jsonify(error=msg), code

    def current_user():
        uid = session.get("uid")
        if not uid:
            return None
        return db().execute("SELECT id,name,email,role FROM users WHERE id=?", (uid,)).fetchone()

    def auth(role=None):
        def deco(fn):
            @wraps(fn)
            def wrapper(*a, **kw):
                user = current_user()
                if not user:
                    return fail("Please log in first.", 401)
                if role and user["role"] != role:
                    return fail("You do not have access to this action.", 403)
                g.user = user
                return fn(*a, **kw)
            return wrapper
        return deco

    def order_dict(row):
        items = db().execute(
            "SELECT item_id,name,price,qty FROM order_items WHERE order_id=?",
            (row["id"],)
        ).fetchall()
        keys = ("id", "token", "order_date", "slot", "status", "total", "payment_method", "payment_status", "created_at")
        d = {k: row[k] for k in keys if k in row.keys()}
        d.setdefault("payment_method", "counter")
        d.setdefault("payment_status", "unpaid")
        d["items"] = [dict(i) for i in items]
        if "customer" in row.keys():
            d["customer"] = row["customer"]
        if "customer_email" in row.keys():
            d["customer_email"] = row["customer_email"]
        return d

    # ---------- pages / health ----------
    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/health")
    def health():
        db().execute("SELECT 1")
        return jsonify(status="ok")

    # ---------- QR Code for Canteen Website ----------
    @app.get("/api/canteen-qr")
    def canteen_qr():
        # Target URL defaults to current host root or configured URL
        target_url = request.args.get("url") or request.host_url
        svg = generate_qr_svg(target_url, scale=8, margin=3)
        return Response(svg, mimetype="image/svg+xml")

    @app.get("/api/canteen-qr/info")
    def canteen_qr_info():
        target_url = request.args.get("url") or request.host_url
        svg = generate_qr_svg(target_url, scale=8, margin=3)
        return jsonify(url=target_url, svg=svg)

    # ---------- auth ----------
    @app.post("/api/register")
    def register():
        d = request.get_json(silent=True) or {}
        name, email, pw = (d.get("name") or "").strip(), (d.get("email") or "").strip().lower(), d.get("password") or ""
        if not name or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return fail("Enter your name and a valid email address.")
        if len(pw) < 6:
            return fail("Password must be at least 6 characters.")
        try:
            cur = db().execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",
                               (name, email, generate_password_hash(pw)))
        except sqlite3.IntegrityError:
            return fail("An account with this email already exists.", 409)
        session["uid"] = cur.lastrowid
        return jsonify(id=cur.lastrowid, name=name, email=email, role="student"), 201

    @app.post("/api/login")
    def login():
        d = request.get_json(silent=True) or {}
        row = db().execute("SELECT * FROM users WHERE email=?", ((d.get("email") or "").strip().lower(),)).fetchone()
        if not row or not check_password_hash(row["password_hash"], d.get("password") or ""):
            return fail("Email or password is incorrect.", 401)
        session["uid"] = row["id"]
        return jsonify(id=row["id"], name=row["name"], email=row["email"], role=row["role"])

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/me")
    def me():
        u = current_user()
        return jsonify(dict(u) if u else None)

    # ---------- menu ----------
    @app.get("/api/menu")
    @auth()
    def menu():
        sql = "SELECT * FROM menu_items"
        params = []
        conditions = []

        is_staff_all = (g.user["role"] == "staff" and request.args.get("all"))
        if not is_staff_all:
            conditions.append("available=1")

        cat = request.args.get("category")
        if cat and cat != "All":
            conditions.append("category=?")
            params.append(cat)

        q = (request.args.get("q") or "").strip()
        if q:
            conditions.append("(name LIKE ? OR description LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sort = request.args.get("sort")
        if sort == "price_asc":
            sql += " ORDER BY price ASC, name ASC"
        elif sort == "price_desc":
            sql += " ORDER BY price DESC, name ASC"
        else:
            sql += " ORDER BY category, name"

        rows = db().execute(sql, params).fetchall()
        return jsonify([dict(r) for r in rows])

    def item_fields(d, partial=False):
        out = {}
        if "name" in d or not partial:
            out["name"] = (d.get("name") or "").strip()
            if not out["name"]:
                raise ValueError("Item name is required.")
        if "category" in d or not partial:
            out["category"] = (d.get("category") or "").strip() or "Snacks"
        if "description" in d:
            out["description"] = str(d["description"])[:300]
        if "image" in d:
            out["image"] = str(d["image"]).strip()
        for f in ("price", "stock"):
            if f in d or not partial:
                try:
                    out[f] = int(d.get(f))
                except (TypeError, ValueError):
                    raise ValueError(f"{f.capitalize()} must be a whole number.")
                if out[f] < 0:
                    raise ValueError(f"{f.capitalize()} cannot be negative.")
        if "available" in d:
            out["available"] = 1 if d["available"] else 0
        return out

    @app.post("/api/menu")
    @auth("staff")
    def add_item():
        try:
            f = item_fields(request.get_json(silent=True) or {})
        except ValueError as e:
            return fail(str(e))
        cols = ",".join(f)
        cur = db().execute(f"INSERT INTO menu_items({cols}) VALUES({','.join('?' * len(f))})", list(f.values()))
        return jsonify(id=cur.lastrowid), 201

    @app.put("/api/menu/<int:item_id>")
    @auth("staff")
    def edit_item(item_id):
        try:
            f = item_fields(request.get_json(silent=True) or {}, partial=True)
        except ValueError as e:
            return fail(str(e))
        if not f:
            return fail("Nothing to update.")
        cur = db().execute(f"UPDATE menu_items SET {','.join(k + '=?' for k in f)} WHERE id=?",
                           [*f.values(), item_id])
        return jsonify(ok=True) if cur.rowcount else fail("Item not found.", 404)

    @app.delete("/api/menu/<int:item_id>")
    @auth("staff")
    def delete_item(item_id):
        # Soft delete keeps past order history intact.
        cur = db().execute("UPDATE menu_items SET available=0, stock=0 WHERE id=?", (item_id,))
        return jsonify(ok=True) if cur.rowcount else fail("Item not found.", 404)

    # ---------- slots ----------
    @app.get("/api/slots")
    @auth()
    def slots():
        date_param = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
        if not DATE_RE.match(date_param):
            return fail("Invalid date format. Expected YYYY-MM-DD.")
        used = {r["slot"]: r["n"] for r in db().execute(
            "SELECT slot, COUNT(*) n FROM orders WHERE order_date=? AND status!='cancelled' GROUP BY slot", (date_param,))}
        cap = app.config["SLOT_CAPACITY"]
        out = []
        for h in range(8, 18):
            for m in (0, 15, 30, 45):
                s = f"{h:02d}:{m:02d}"
                out.append({"slot": s, "used": used.get(s, 0), "capacity": cap, "date": date_param})
        return jsonify(out)

    # ---------- orders ----------
    @app.post("/api/orders")
    @auth("student")
    def place_order():
        d = request.get_json(silent=True) or {}
        slot, lines = d.get("slot") or "", d.get("items") or []
        today = datetime.now().strftime("%Y-%m-%d")
        order_date = (d.get("date") or d.get("order_date") or today).strip()

        if not DATE_RE.match(order_date):
            return fail("Invalid order date format. Expected YYYY-MM-DD.")
        if order_date < today:
            return fail("Cannot place an order for a past date.")
        # Limit future booking to max 7 days ahead
        max_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        if order_date > max_date:
            return fail("Cannot place orders more than 7 days in advance.")

        if not SLOT_RE.match(slot):
            return fail("Choose a pickup time slot.")
        if not isinstance(lines, list) or not lines:
            return fail("Add at least one item to your order.")

        merged = {}
        for ln in lines:
            try:
                iid, qty = int(ln["item_id"]), int(ln["qty"])
            except (KeyError, TypeError, ValueError):
                return fail("Invalid order items.")
            if qty < 1 or qty > 10:
                return fail("Quantity must be between 1 and 10 per item.")
            merged[iid] = merged.get(iid, 0) + qty

        conn = db()
        conn.execute("BEGIN IMMEDIATE")
        try:
            n = conn.execute("SELECT COUNT(*) FROM orders WHERE order_date=? AND slot=? AND status!='cancelled'",
                             (order_date, slot)).fetchone()[0]
            if n >= app.config["SLOT_CAPACITY"]:
                raise ValueError(f"The {slot} slot is full for {order_date}. Pick another time.")
            total, rows = 0, []
            for iid, qty in merged.items():
                it = conn.execute("SELECT * FROM menu_items WHERE id=? AND available=1", (iid,)).fetchone()
                if not it:
                    raise ValueError("An item in your cart is no longer available.")
                cur = conn.execute("UPDATE menu_items SET stock=stock-? WHERE id=? AND stock>=?", (qty, iid, qty))
                if not cur.rowcount:
                    raise ValueError(f"Only {it['stock']} left of {it['name']}.")
                total += it["price"] * qty
                rows.append((iid, it["name"], it["price"], qty))

            token = conn.execute(
                "SELECT COALESCE(MAX(token),0)+1 FROM orders WHERE order_date=?", (order_date,)
            ).fetchone()[0]

            oid = conn.execute(
                "INSERT INTO orders(user_id,token,order_date,slot,total,payment_method,payment_status,created_at) "
                "VALUES(?,?,?,?,?,'counter','unpaid',?)",
                (g.user["id"], token, order_date, slot, total, datetime.now().isoformat(timespec="seconds"))
            ).lastrowid

            conn.executemany(
                "INSERT INTO order_items(order_id,item_id,name,price,qty) VALUES(?,?,?,?,?)",
                [(oid, *r) for r in rows]
            )
            conn.execute("COMMIT")
        except ValueError as e:
            conn.execute("ROLLBACK")
            return fail(str(e), 409)
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

        row = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        return jsonify(order_dict(row)), 201

    @app.get("/api/orders")
    @auth()
    def list_orders():
        if g.user["role"] == "staff":
            date_filter = request.args.get("date")
            all_dates = request.args.get("all")
            if all_dates:
                rows = db().execute(
                    "SELECT o.*, u.name AS customer, u.email AS customer_email FROM orders o "
                    "JOIN users u ON u.id=o.user_id "
                    "ORDER BY o.order_date DESC, o.slot ASC, o.token ASC"
                ).fetchall()
            elif date_filter:
                rows = db().execute(
                    "SELECT o.*, u.name AS customer, u.email AS customer_email FROM orders o "
                    "JOIN users u ON u.id=o.user_id "
                    "WHERE o.order_date=? ORDER BY o.slot, o.token", (date_filter,)
                ).fetchall()
            else:
                today = datetime.now().strftime("%Y-%m-%d")
                rows = db().execute(
                    "SELECT o.*, u.name AS customer, u.email AS customer_email FROM orders o "
                    "JOIN users u ON u.id=o.user_id "
                    "WHERE o.order_date>=? ORDER BY o.order_date ASC, o.slot ASC, o.token ASC", (today,)
                ).fetchall()
        else:
            rows = db().execute(
                "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 50",
                (g.user["id"],)
            ).fetchall()
        return jsonify([order_dict(r) for r in rows])

    @app.post("/api/orders/<int:order_id>/status")
    @auth()
    def set_status(order_id):
        new = ((request.get_json(silent=True) or {}).get("status") or "").lower()
        conn = db()
        conn.execute("BEGIN IMMEDIATE")
        try:
            o = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if not o or (g.user["role"] == "student" and o["user_id"] != g.user["id"]):
                conn.execute("ROLLBACK")
                return fail("Order not found.", 404)
            if g.user["role"] == "student" and new != "cancelled":
                conn.execute("ROLLBACK")
                return fail("You can only cancel your own order.", 403)

            allowed = FLOW.get(o["status"], [])
            if new not in allowed:
                conn.execute("ROLLBACK")
                return fail(f"Cannot change an order from {o['status']} to {new}.", 409)

            if new == "cancelled":
                for it in conn.execute("SELECT item_id,qty FROM order_items WHERE order_id=?", (order_id,)):
                    conn.execute("UPDATE menu_items SET stock=stock+? WHERE id=?", (it["qty"], it["item_id"]))
            conn.execute("UPDATE orders SET status=? WHERE id=?", (new, order_id))
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        return jsonify(ok=True, status=new)

    @app.post("/api/orders/<int:order_id>/payment")
    @auth("staff")
    def set_payment_status(order_id):
        d = request.get_json(silent=True) or {}
        new_status = (d.get("payment_status") or "paid").lower()
        if new_status not in ("paid", "unpaid"):
            return fail("Invalid payment status. Must be 'paid' or 'unpaid'.")
        cur = db().execute("UPDATE orders SET payment_status=? WHERE id=?", (new_status, order_id))
        if not cur.rowcount:
            return fail("Order not found.", 404)
        row = db().execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return jsonify(order_dict(row))

    @app.get("/api/stats")
    @auth("staff")
    def stats():
        target_date = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
        r = db().execute(
            "SELECT COUNT(*) orders, "
            "COALESCE(SUM(CASE WHEN status!='cancelled' THEN total END),0) revenue, "
            "COALESCE(SUM(status IN ('placed','accepted','preparing','ready')),0) pending, "
            "COALESCE(SUM(payment_status='paid' AND status!='cancelled'),0) paid_orders, "
            "COALESCE(SUM(payment_status='unpaid' AND status!='cancelled'),0) unpaid_orders "
            "FROM orders WHERE order_date=?",
            (target_date,)
        ).fetchone()
        low = db().execute("SELECT id,name,stock,category FROM menu_items WHERE available=1 AND stock<=5 ORDER BY stock").fetchall()
        return jsonify(**dict(r), low_stock=[dict(x) for x in low], date=target_date)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
