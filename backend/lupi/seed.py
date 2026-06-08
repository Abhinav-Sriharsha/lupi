"""
Lupi database seed script.

Usage:
    cd backend
    python -m lupi.seed

Step 1: Prints DROP + CREATE SQL — run that in the Supabase SQL editor first.
Step 2: Inserts realistic demo data via the Supabase Python client.
"""

import os
import sys
import uuid
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env from backend/ ────────────────────────────────────────────────────
_here = Path(__file__).resolve().parent          # backend/lupi/
_env  = _here.parent / ".env"                   # backend/.env
load_dotenv(dotenv_path=_env)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("[LUPI] ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in backend/.env")
    sys.exit(1)

from supabase import create_client
sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ── Section 1 — Print DDL (user runs this in Supabase SQL editor) ──────────────

print("""
-- Run this in Supabase SQL editor FIRST, then run this script

DROP TABLE IF EXISTS lupi_ticket_messages, lupi_support_tickets, lupi_refunds,
  lupi_delivery_tracking, lupi_order_items, lupi_orders, lupi_promotions,
  lupi_menu_items, lupi_menu_categories, lupi_restaurants, lupi_dasher_ratings,
  lupi_dashers, lupi_payment_methods, lupi_addresses, lupi_customers CASCADE;

CREATE TABLE lupi_customers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  is_dashpass_member BOOLEAN DEFAULT FALSE,
  dashpass_since TIMESTAMPTZ,
  credits_balance DECIMAL(10,2) DEFAULT 0,
  total_orders INT DEFAULT 0,
  total_spent DECIMAL(10,2) DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE lupi_addresses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id UUID REFERENCES lupi_customers(id) ON DELETE CASCADE,
  label TEXT,
  street TEXT NOT NULL,
  city TEXT NOT NULL,
  state TEXT NOT NULL,
  zip TEXT NOT NULL,
  lat DECIMAL(9,6),
  lng DECIMAL(9,6),
  delivery_instructions TEXT,
  is_default BOOLEAN DEFAULT FALSE
);

CREATE TABLE lupi_payment_methods (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id UUID REFERENCES lupi_customers(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  last_four TEXT,
  brand TEXT,
  is_default BOOLEAN DEFAULT FALSE
);

CREATE TABLE lupi_dashers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  phone TEXT UNIQUE NOT NULL,
  vehicle_type TEXT NOT NULL,
  vehicle_make TEXT,
  vehicle_color TEXT,
  rating DECIMAL(3,2) DEFAULT 4.80,
  total_deliveries INT DEFAULT 0,
  is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE lupi_dasher_ratings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dasher_id UUID REFERENCES lupi_dashers(id),
  order_id UUID,
  rating INT CHECK (rating BETWEEN 1 AND 5),
  comment TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE lupi_restaurants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  cuisine TEXT NOT NULL,
  address TEXT NOT NULL,
  city TEXT NOT NULL,
  phone TEXT,
  rating DECIMAL(3,2) DEFAULT 4.50,
  price_range INT DEFAULT 2,
  estimated_prep_minutes INT DEFAULT 20,
  is_open BOOLEAN DEFAULT TRUE,
  delivery_fee DECIMAL(5,2) DEFAULT 3.99,
  min_order DECIMAL(6,2) DEFAULT 10.00
);

CREATE TABLE lupi_menu_categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id UUID REFERENCES lupi_restaurants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  sort_order INT DEFAULT 0
);

CREATE TABLE lupi_menu_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  restaurant_id UUID REFERENCES lupi_restaurants(id) ON DELETE CASCADE,
  category_id UUID REFERENCES lupi_menu_categories(id),
  name TEXT NOT NULL,
  description TEXT,
  price DECIMAL(8,2) NOT NULL,
  is_available BOOLEAN DEFAULT TRUE,
  calories INT
);

CREATE TABLE lupi_orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_number TEXT UNIQUE NOT NULL,
  customer_id UUID REFERENCES lupi_customers(id),
  restaurant_id UUID REFERENCES lupi_restaurants(id),
  dasher_id UUID REFERENCES lupi_dashers(id),
  delivery_address_id UUID REFERENCES lupi_addresses(id),
  payment_method_id UUID REFERENCES lupi_payment_methods(id),
  status TEXT NOT NULL DEFAULT 'pending',
  subtotal DECIMAL(10,2) NOT NULL,
  delivery_fee DECIMAL(6,2) NOT NULL,
  service_fee DECIMAL(6,2) NOT NULL,
  tip DECIMAL(6,2) NOT NULL,
  total DECIMAL(10,2) NOT NULL,
  special_instructions TEXT,
  placed_at TIMESTAMPTZ DEFAULT NOW(),
  estimated_pickup_at TIMESTAMPTZ,
  picked_up_at TIMESTAMPTZ,
  estimated_delivery_at TIMESTAMPTZ,
  delivered_at TIMESTAMPTZ,
  cancelled_at TIMESTAMPTZ,
  cancellation_reason TEXT
);

CREATE TABLE lupi_order_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id UUID REFERENCES lupi_orders(id) ON DELETE CASCADE,
  menu_item_id UUID REFERENCES lupi_menu_items(id),
  name TEXT NOT NULL,
  quantity INT NOT NULL DEFAULT 1,
  unit_price DECIMAL(8,2) NOT NULL,
  customizations JSONB DEFAULT '{}',
  notes TEXT
);

CREATE TABLE lupi_delivery_tracking (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id UUID REFERENCES lupi_orders(id) ON DELETE CASCADE,
  dasher_id UUID REFERENCES lupi_dashers(id),
  event TEXT NOT NULL,
  lat DECIMAL(9,6),
  lng DECIMAL(9,6),
  note TEXT,
  recorded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE lupi_refunds (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id UUID REFERENCES lupi_orders(id),
  customer_id UUID REFERENCES lupi_customers(id),
  amount DECIMAL(10,2) NOT NULL,
  type TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  issued_by TEXT DEFAULT 'lupi_agent',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ
);

CREATE TABLE lupi_promotions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT UNIQUE NOT NULL,
  type TEXT NOT NULL,
  value DECIMAL(8,2) NOT NULL,
  min_order DECIMAL(8,2) DEFAULT 0,
  used_by UUID REFERENCES lupi_customers(id),
  expires_at TIMESTAMPTZ
);

CREATE TABLE lupi_support_tickets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id UUID REFERENCES lupi_orders(id),
  customer_id UUID REFERENCES lupi_customers(id),
  issue_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  resolution TEXT,
  refund_id UUID REFERENCES lupi_refunds(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  resolved_at TIMESTAMPTZ
);

CREATE TABLE lupi_ticket_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id UUID REFERENCES lupi_support_tickets(id) ON DELETE CASCADE,
  sender TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
""")

input("\n[LUPI] Press ENTER after you have run the SQL above in Supabase → ")

# ── Helpers ────────────────────────────────────────────────────────────────────

def uid() -> str:
    return str(uuid.uuid4())

def now() -> datetime:
    return datetime.now(timezone.utc)

def fmt(dt: datetime) -> str:
    return dt.isoformat()

def order_num() -> str:
    return f"LP-{random.randint(10000, 99999)}"

def calc_financials(subtotal: float, delivery_fee: float):
    service_fee = round(subtotal * 0.10, 2)
    tip         = round(subtotal * 0.15, 2)
    total       = round(subtotal + delivery_fee + service_fee + tip, 2)
    return service_fee, tip, total

# ── Section 2 — Seed Data ──────────────────────────────────────────────────────

print("[LUPI] Seeding customers...")

# ── Customers ──────────────────────────────────────────────────────────────────
customer_rows = [
    # phone, email, first, last, dashpass, credits, total_orders
    ("+14155550101", "maya.patel@gmail.com",    "Maya",   "Patel",    True,  12.50, 47),
    ("+14155550102", "jordan.r@gmail.com",       "Jordan", "Rivera",   False,  0.00, 14),
    ("+14155550103", "priya.sharma@gmail.com",   "Priya",  "Sharma",   True,   5.00, 31),
    ("+14155550104", "mjohnson@gmail.com",        "Marcus", "Johnson",  False,  0.00,  3),
    ("+14155550105", "aisha.w@gmail.com",         "Aisha",  "Williams", True,  15.00, 22),
    ("+14155550106", "k.zhang@gmail.com",         "Kevin",  "Zhang",    False,  2.50,  9),
    ("+14155550107", "sofia.r@gmail.com",         "Sofia",  "Reyes",    True,   8.00, 38),
    ("+14155550108", "e.cohen@gmail.com",         "Eli",    "Cohen",    False,  0.00,  6),
]

customer_ids = []
for phone, email, first, last, dashpass, credits, total_orders in customer_rows:
    cid = uid()
    customer_ids.append(cid)
    dashpass_since = fmt(now() - timedelta(days=random.randint(90, 730))) if dashpass else None
    sb.table("lupi_customers").insert({
        "id": cid,
        "phone": phone,
        "email": email,
        "first_name": first,
        "last_name": last,
        "is_dashpass_member": dashpass,
        "dashpass_since": dashpass_since,
        "credits_balance": credits,
        "total_orders": total_orders,
        "total_spent": round(total_orders * random.uniform(18, 35), 2),
    }).execute()

# ── Addresses (one per customer, San Jose) ─────────────────────────────────────
print("[LUPI] Seeding addresses...")

streets = [
    ("123 Willow Ave",      37.338207, -121.886330),
    ("456 Market St",       37.334789, -121.888423),
    ("789 Almaden Blvd",    37.318544, -121.882851),
    ("1010 N First St",     37.352094, -121.903416),
    ("234 Santana Row",     37.321621, -121.947243),
    ("567 Blossom Hill Rd", 37.255060, -121.841660),
    ("890 Meridian Ave",    37.295812, -121.884561),
    ("321 Lincoln Ave",     37.310450, -121.841230),
]
instructions = [
    "Leave at door", "Ring doorbell", "Call on arrival",
    "Leave at door, no knock", "Text when here", "Gate code #4821",
    "Apartment 3B, use side entrance", "Leave with front desk",
]
labels = ["Home", "Apartment", "House", "Condo", "Home", "Apartment", "Home", "Condo"]

address_ids = []
for i, cid in enumerate(customer_ids):
    aid = uid()
    address_ids.append(aid)
    street, lat, lng = streets[i]
    sb.table("lupi_addresses").insert({
        "id": aid,
        "customer_id": cid,
        "label": labels[i],
        "street": street,
        "city": "San Jose",
        "state": "CA",
        "zip": f"9511{i}",
        "lat": lat,
        "lng": lng,
        "delivery_instructions": instructions[i],
        "is_default": True,
    }).execute()

# ── Payment Methods ────────────────────────────────────────────────────────────
print("[LUPI] Seeding payment methods...")

payment_configs = [
    ("card", "4242", "Visa"),
    ("card", "5555", "Mastercard"),
    ("card", "3782", "Amex"),
    ("apple_pay", None, "Apple Pay"),
    ("card", "4111", "Visa"),
    ("card", "5105", "Mastercard"),
    ("card", "3714", "Amex"),
    ("apple_pay", None, "Apple Pay"),
]

payment_ids = []
for i, cid in enumerate(customer_ids):
    pid = uid()
    payment_ids.append(pid)
    ptype, last4, brand = payment_configs[i]
    sb.table("lupi_payment_methods").insert({
        "id": pid,
        "customer_id": cid,
        "type": ptype,
        "last_four": last4,
        "brand": brand,
        "is_default": True,
    }).execute()

# ── Dashers ────────────────────────────────────────────────────────────────────
print("[LUPI] Seeding dashers...")

dasher_data = [
    ("Carlos", "Mendez",   "+14085550201", "car",    "Toyota",    "Silver", 4.92, 2341),
    ("Nina",   "Pham",     "+14085550202", "car",    "Honda",     "White",  4.88, 1876),
    ("Andre",  "Thompson", "+14085550203", "bike",   None,        None,     4.75,  943),
    ("Leila",  "Ito",      "+14085550204", "car",    "Subaru",    "Blue",   4.95, 3102),
    ("Raj",    "Kapoor",   "+14085550205", "scooter",None,        None,     4.61,  512),
    ("Megan",  "Torres",   "+14085550206", "car",    "Chevrolet", "Black",  4.83, 1654),
]

dasher_ids = []
for first, last, phone, vtype, vmake, vcolor, rating, deliveries in dasher_data:
    did = uid()
    dasher_ids.append(did)
    sb.table("lupi_dashers").insert({
        "id": did,
        "first_name": first,
        "last_name": last,
        "phone": phone,
        "vehicle_type": vtype,
        "vehicle_make": vmake,
        "vehicle_color": vcolor,
        "rating": rating,
        "total_deliveries": deliveries,
        "is_active": True,
    }).execute()

# ── Restaurants + Menu ─────────────────────────────────────────────────────────
print("[LUPI] Seeding restaurants and menus...")

# Each entry: (name, cuisine, address, rating, price_range, prep_min, delivery_fee, min_order, phone, categories)
# categories: list of (cat_name, sort_order, [items])
# items: (name, description, price, calories)

restaurant_menus = [
    # 0 — Chipotle
    {
        "name": "Chipotle Mexican Grill",
        "cuisine": "Mexican",
        "address": "300 S 1st St",
        "rating": 4.30,
        "price_range": 2,
        "prep_min": 12,
        "delivery_fee": 2.99,
        "min_order": 10.00,
        "phone": "+14089001001",
        "categories": [
            ("Burritos & Bowls", 0, [
                ("Chicken Burrito Bowl", "White/brown rice, black beans, grilled chicken, pico, cheese, sour cream", 12.75, 710),
                ("Steak Burrito", "Flour tortilla, steak, fajita veggies, guac, salsa", 13.25, 830),
                ("Sofritas Bowl", "Plant-based tofu, brown rice, corn salsa, guacamole", 11.50, 640),
                ("Barbacoa Burrito Bowl", "Braised beef, cilantro-lime rice, pinto beans, sour cream", 13.50, 760),
            ]),
            ("Tacos", 1, [
                ("Chicken Soft Tacos (3)", "Grilled chicken, cheese, lettuce, pico de gallo", 11.75, 520),
                ("Steak Crispy Tacos (3)", "Crisped corn shells, steak, sour cream, guac", 12.50, 610),
            ]),
            ("Extras & Drinks", 2, [
                ("Chips & Guacamole", "House-made chips with fresh guac", 5.25, 480),
                ("Chips & Queso", "White cheddar queso blanco", 4.75, 380),
                ("Mexican Coke (12oz)", "Cane-sugar Coca-Cola", 3.25, 140),
            ]),
        ],
    },
    # 1 — Din Tai Fung
    {
        "name": "Din Tai Fung",
        "cuisine": "Asian Fusion",
        "address": "088 Westfield Valley Fair Mall",
        "rating": 4.70,
        "price_range": 3,
        "prep_min": 25,
        "delivery_fee": 4.99,
        "min_order": 20.00,
        "phone": "+14082001002",
        "categories": [
            ("Soup Dumplings", 0, [
                ("Pork Xiao Long Bao (10pc)", "Classic pork soup dumplings, housemade dipping sauce", 17.00, 420),
                ("Shrimp & Pork XLB (10pc)", "Delicate shrimp-pork blend in thin skin", 19.50, 450),
                ("Truffle Xiao Long Bao (6pc)", "Pork with black truffle, premium dipping sauce", 22.00, 370),
            ]),
            ("Noodles & Rice", 1, [
                ("Dan Dan Noodles", "Sesame-chili sauce, minced pork, peanuts, scallions", 15.00, 580),
                ("Braised Pork Chop Fried Rice", "Wok-fried jasmine rice, crispy pork chop, egg", 16.50, 720),
                ("Shrimp Fried Rice", "House fried rice with tiger shrimp and vegetables", 17.00, 680),
            ]),
            ("Appetizers", 2, [
                ("Cucumber Salad", "Smashed cucumbers, garlic, rice vinegar, sesame oil", 8.50, 120),
                ("Pan-Fried Pork Chop (2pc)", "Crispy golden pork with soy-garlic glaze", 14.00, 390),
            ]),
            ("Desserts", 3, [
                ("Red Bean Xiao Long Bao (6pc)", "Sweet red bean soup dumplings", 9.50, 280),
                ("Taro Cake", "Steamed taro cake with house sweet sauce", 8.00, 240),
            ]),
        ],
    },
    # 2 — Shake Shack
    {
        "name": "Shake Shack",
        "cuisine": "American",
        "address": "180 E Tasman Dr",
        "rating": 4.50,
        "price_range": 2,
        "prep_min": 10,
        "delivery_fee": 2.99,
        "min_order": 10.00,
        "phone": "+14082001003",
        "categories": [
            ("Burgers", 0, [
                ("ShackBurger", "Cheeseburger with ShackSauce, lettuce, tomato, pickles", 9.29, 560),
                ("SmokeShack", "American cheese, applewood-smoked bacon, cherry peppers, ShackSauce", 11.09, 640),
                ("Shroom Burger", "Crisp-fried portobello, muenster & cheddar, ShackSauce", 10.29, 590),
                ("Double ShackBurger", "Two beef patties, double cheese, ShackSauce", 13.29, 770),
            ]),
            ("Chicken", 1, [
                ("Chick'n Shack", "Crispy fried chicken, pickles, buttermilk herb mayo", 9.99, 620),
                ("Spicy Chick'n Shack", "Hot sauce-marinated crispy chicken, pickled peppers", 10.29, 640),
            ]),
            ("Fries & Sides", 2, [
                ("Crinkle-Cut Fries", "Seasoned crinkle-cut fries", 4.69, 420),
                ("Cheese Fries", "Crinkle fries with cheddar cheese sauce", 5.69, 530),
            ]),
            ("Shakes & Drinks", 3, [
                ("Vanilla Shake", "Hand-spun vanilla custard shake", 7.29, 680),
                ("Chocolate Shake", "Hand-spun chocolate custard shake", 7.29, 700),
                ("Lemonade", "Fresh-squeezed lemonade", 4.29, 180),
            ]),
        ],
    },
    # 3 — Sweetgreen
    {
        "name": "Sweetgreen",
        "cuisine": "Salads/Healthy",
        "address": "378 Santana Row",
        "rating": 4.40,
        "price_range": 2,
        "prep_min": 15,
        "delivery_fee": 3.49,
        "min_order": 12.00,
        "phone": "+14082001004",
        "categories": [
            ("Salads", 0, [
                ("Harvest Bowl", "Wild rice, roasted sweet potato, apples, candied walnuts, balsamic vinaigrette", 14.95, 705),
                ("Garden Cobb", "Roasted chicken, avocado, hard-boiled egg, tomatoes, blue cheese", 15.45, 580),
                ("Guacamole Greens", "Arugula, avocado, black beans, corn, lime cilantro jalapeño vinaigrette", 13.95, 490),
                ("Buffalo Chicken Bowl", "Warm quinoa, buffalo chicken, carrots, celery, blue cheese", 15.95, 640),
            ]),
            ("Warm Bowls", 1, [
                ("Crispy Rice Bowl", "Sushi rice, roasted chicken, edamame, cucumber, miso sesame dressing", 14.95, 620),
                ("Shroomami", "Wild rice, roasted mushrooms, tofu, edamame, miso dressing", 13.95, 530),
            ]),
            ("Extras", 2, [
                ("Side of Avocado", "Fresh sliced avocado", 3.50, 120),
                ("Sparkling Water", "Unsweetened sparkling water", 2.75, 0),
            ]),
        ],
    },
    # 4 — The Halal Guys
    {
        "name": "The Halal Guys",
        "cuisine": "Middle Eastern",
        "address": "1 Paseo de San Antonio",
        "rating": 4.45,
        "price_range": 1,
        "prep_min": 18,
        "delivery_fee": 2.49,
        "min_order": 10.00,
        "phone": "+14082001005",
        "categories": [
            ("Platters", 0, [
                ("Chicken over Rice Platter", "Halal chicken, saffron-spiced basmati rice, pita, white sauce, hot sauce", 13.99, 890),
                ("Falafel Platter", "Crispy falafel, hummus, salad, pita, white sauce", 12.99, 750),
                ("Combo Platter (Chicken & Gyro)", "Half chicken, half gyro, rice, pita, sauces", 15.99, 1020),
                ("Gyro over Rice Platter", "Seasoned beef gyro, basmati rice, pita, sauces", 14.99, 960),
            ]),
            ("Sandwiches", 1, [
                ("Chicken Sandwich", "Grilled chicken, pita, lettuce, tomato, white sauce", 10.99, 580),
                ("Falafel Sandwich", "Falafel, hummus, pickled vegetables in pita", 9.99, 490),
            ]),
            ("Extras", 2, [
                ("Extra White Sauce", "Creamy garlic-herb dipping sauce", 0.99, 80),
                ("Baklava (2pc)", "Honey-walnut phyllo pastry", 4.49, 320),
                ("Can of Soda", "Pepsi, Diet Pepsi, or Water", 1.99, 140),
            ]),
        ],
    },
    # 5 — Philz Coffee
    {
        "name": "Philz Coffee",
        "cuisine": "Coffee/Breakfast",
        "address": "201 S 1st St",
        "rating": 4.65,
        "price_range": 2,
        "prep_min": 8,
        "delivery_fee": 1.99,
        "min_order": 8.00,
        "phone": "+14082001006",
        "categories": [
            ("Signature Coffees", 0, [
                ("Mint Mojito", "Medium roast with fresh mint and cream", 6.75, 120),
                ("Tesora", "Smooth medium-dark blend, sweet and creamy finish", 6.50, 110),
                ("Iced Philharmonic", "Bright, lively blend over ice with cream", 7.25, 130),
                ("Silken Splendor", "Light, velvety roast with sweet cream", 6.75, 115),
            ]),
            ("Food", 1, [
                ("Avocado Toast", "Sourdough, smashed avocado, everything bagel seasoning, lemon", 11.50, 380),
                ("Blueberry Scone", "House-baked scone with wild blueberries and lemon glaze", 4.75, 340),
                ("Egg & Cheese Croissant", "Butter croissant with cage-free egg and cheddar", 8.50, 420),
                ("Overnight Oats", "Oat milk oats, chia seeds, honey, fresh berries", 7.50, 310),
            ]),
            ("Cold Drinks", 2, [
                ("Iced Latte (Custom)", "Choose your roast, iced with whole milk", 6.25, 150),
                ("Cold Brew", "Slow-steeped 20-hour cold brew, black or with cream", 5.75, 10),
            ]),
        ],
    },
    # 6 — Curry Up Now
    {
        "name": "Curry Up Now",
        "cuisine": "Indian",
        "address": "129 S Murphy Ave",
        "rating": 4.55,
        "price_range": 2,
        "prep_min": 22,
        "delivery_fee": 3.99,
        "min_order": 15.00,
        "phone": "+14082001007",
        "categories": [
            ("Burritos", 0, [
                ("Chicken Tikka Masala Burrito", "Tikka masala chicken, basmati rice, raita, mint chutney in a flour tortilla", 15.50, 780),
                ("Paneer Tikka Burrito", "Grilled paneer, tikka sauce, basmati, chutney", 14.50, 710),
                ("Saag Lamb Burrito", "Braised lamb, saag (spinach-cream), rice, raita", 16.00, 820),
            ]),
            ("Bowls & Thalis", 1, [
                ("Chicken Tikka Masala Bowl", "Rich tomato-cream curry, basmati rice, naan", 14.50, 740),
                ("Chana Masala Bowl", "Spiced chickpeas, rice, pickled onions, naan", 12.50, 580),
                ("Lamb Rogan Josh Bowl", "Slow-braised lamb, aromatic gravy, rice, naan", 17.00, 870),
            ]),
            ("Appetizers & Sides", 2, [
                ("Samosa Chaat (2pc)", "Crispy samosas topped with yogurt, chutneys, sev", 9.50, 380),
                ("Garlic Naan (2pc)", "Tandoor-baked flatbread with garlic butter", 5.00, 280),
                ("Mango Lassi", "Yogurt, fresh mango, cardamom, pinch of salt", 5.50, 220),
            ]),
            ("Desserts", 3, [
                ("Gulab Jamun (3pc)", "Milk-solid dumplings in rose-saffron syrup", 6.50, 310),
                ("Kulfi (Pistachio)", "Traditional Indian ice cream, cardamom, pistachio", 5.50, 260),
            ]),
        ],
    },
    # 7 — Mendocino Farms
    {
        "name": "Mendocino Farms",
        "cuisine": "Sandwiches",
        "address": "268 Santana Row",
        "rating": 4.60,
        "price_range": 2,
        "prep_min": 14,
        "delivery_fee": 3.49,
        "min_order": 12.00,
        "phone": "+14082001008",
        "categories": [
            ("Signature Sandwiches", 0, [
                ("Avocado & Quinoa Salad Sandwich", "Smashed avo, tri-colored quinoa, arugula, lemon tahini, sourdough", 14.50, 590),
                ("Kurobuta Pork Belly Banh Mi", "Kurobuta pork belly, pickled daikon, jalapeño, cilantro, baguette", 15.50, 720),
                ("Spicy Tuna Crunch Sandwich", "Ahi tuna, cucumber, avocado, spicy aioli, sesame, brioche", 16.00, 640),
                ("Basil-Parm Chicken Sandwich", "Fried chicken, basil aioli, parmesan, arugula, brioche", 15.00, 680),
            ]),
            ("Salads", 1, [
                ("Supergreen Goddess", "Kale, shredded Brussels, avocado, green goddess dressing, almonds", 14.00, 460),
                ("Baja Bowl", "Roasted chicken, brown rice, avocado, black beans, lime vinaigrette", 15.50, 680),
            ]),
            ("Soups & Sides", 2, [
                ("Tomato Bisque (Cup)", "Slow-roasted tomato, cream, basil oil", 6.50, 220),
                ("Kale Caesar Salad (Side)", "Lacinato kale, parmesan, croutons, house Caesar", 6.00, 280),
                ("Sea Salt Kettle Chips", "Hand-cooked kettle chips, sea salt", 2.75, 150),
            ]),
        ],
    },
]

restaurant_ids = []
# restaurant_id → { cat_name → [item_dict] }
restaurant_menu_map = {}

for rm in restaurant_menus:
    rid = uid()
    restaurant_ids.append(rid)
    sb.table("lupi_restaurants").insert({
        "id": rid,
        "name": rm["name"],
        "cuisine": rm["cuisine"],
        "address": rm["address"],
        "city": "San Jose",
        "phone": rm["phone"],
        "rating": rm["rating"],
        "price_range": rm["price_range"],
        "estimated_prep_minutes": rm["prep_min"],
        "is_open": True,
        "delivery_fee": rm["delivery_fee"],
        "min_order": rm["min_order"],
    }).execute()

    restaurant_menu_map[rid] = {}
    for cat_name, sort_order, items in rm["categories"]:
        cid_cat = uid()
        sb.table("lupi_menu_categories").insert({
            "id": cid_cat,
            "restaurant_id": rid,
            "name": cat_name,
            "sort_order": sort_order,
        }).execute()

        item_list = []
        for item_name, desc, price, cal in items:
            iid = uid()
            sb.table("lupi_menu_items").insert({
                "id": iid,
                "restaurant_id": rid,
                "category_id": cid_cat,
                "name": item_name,
                "description": desc,
                "price": price,
                "is_available": True,
                "calories": cal,
            }).execute()
            item_list.append({"id": iid, "name": item_name, "price": price})

        restaurant_menu_map[rid][cat_name] = item_list

def get_items(rid, cat_name):
    return restaurant_menu_map[rid][cat_name]

def first_items(rid, cat_name, n=2):
    return get_items(rid, cat_name)[:n]

# ── Orders (8 scenarios) ────────────────────────────────────────────────────────
print("[LUPI] Seeding orders...")

# Shortcuts
r_chipotle    = restaurant_ids[0]
r_dtf         = restaurant_ids[1]
r_shake       = restaurant_ids[2]
r_sweet       = restaurant_ids[3]
r_halal       = restaurant_ids[4]
r_philz       = restaurant_ids[5]
r_curry       = restaurant_ids[6]
r_mendo       = restaurant_ids[7]

preps = [rm["prep_min"] for rm in restaurant_menus]   # indexed same as restaurant_ids
dfees = [rm["delivery_fee"] for rm in restaurant_menus]

orders = []  # will collect (order_id, customer_id) for tickets

# ── 1. Maya Patel — Chipotle — DELIVERED LATE (+50 min) ────────────────────────
idx = 0
rid = r_chipotle
placed = now() - timedelta(hours=2, minutes=30)
est_delivery = placed + timedelta(minutes=preps[0] + 20)
picked_up    = placed + timedelta(minutes=preps[0] + 3)
delivered    = est_delivery + timedelta(minutes=50)   # 50 min late

items_used = first_items(rid, "Burritos & Bowls", 2) + first_items(rid, "Extras & Drinks", 1)
subtotal = round(sum(it["price"] for it in items_used), 2)
svc, tip, total = calc_financials(subtotal, dfees[0])
oid = uid()
sb.table("lupi_orders").insert({
    "id": oid,
    "order_number": order_num(),
    "customer_id": customer_ids[idx],
    "restaurant_id": rid,
    "dasher_id": dasher_ids[0],
    "delivery_address_id": address_ids[idx],
    "payment_method_id": payment_ids[idx],
    "status": "delivered",
    "subtotal": subtotal,
    "delivery_fee": dfees[0],
    "service_fee": svc,
    "tip": tip,
    "total": total,
    "placed_at": fmt(placed),
    "estimated_pickup_at": fmt(placed + timedelta(minutes=preps[0])),
    "picked_up_at": fmt(picked_up),
    "estimated_delivery_at": fmt(est_delivery),
    "delivered_at": fmt(delivered),
}).execute()
for it in items_used:
    sb.table("lupi_order_items").insert({
        "id": uid(), "order_id": oid, "menu_item_id": it["id"],
        "name": it["name"], "quantity": 1, "unit_price": it["price"],
    }).execute()
orders.append((oid, customer_ids[idx], rid, "late_delivery"))

# ── 2. Jordan Rivera — Shake Shack — MISSING ITEMS ─────────────────────────────
idx = 1
rid = r_shake
placed = now() - timedelta(hours=1, minutes=10)
est_delivery = placed + timedelta(minutes=preps[2] + 20)
picked_up    = placed + timedelta(minutes=preps[2] + 2)
delivered    = est_delivery + timedelta(minutes=6)

# 2 items ordered, customer will claim 1 is missing
shake_items = first_items(rid, "Burgers", 2)
subtotal = round(sum(it["price"] for it in shake_items), 2)
svc, tip, total = calc_financials(subtotal, dfees[2])
oid = uid()
sb.table("lupi_orders").insert({
    "id": oid,
    "order_number": order_num(),
    "customer_id": customer_ids[idx],
    "restaurant_id": rid,
    "dasher_id": dasher_ids[1],
    "delivery_address_id": address_ids[idx],
    "payment_method_id": payment_ids[idx],
    "status": "delivered",
    "subtotal": subtotal,
    "delivery_fee": dfees[2],
    "service_fee": svc,
    "tip": tip,
    "total": total,
    "placed_at": fmt(placed),
    "estimated_pickup_at": fmt(placed + timedelta(minutes=preps[2])),
    "picked_up_at": fmt(picked_up),
    "estimated_delivery_at": fmt(est_delivery),
    "delivered_at": fmt(delivered),
}).execute()
for it in shake_items:
    sb.table("lupi_order_items").insert({
        "id": uid(), "order_id": oid, "menu_item_id": it["id"],
        "name": it["name"], "quantity": 1, "unit_price": it["price"],
    }).execute()
orders.append((oid, customer_ids[idx], rid, "missing_items"))

# ── 3. Priya Sharma — Din Tai Fung — OUT FOR DELIVERY (never arrived) ──────────
idx = 2
rid = r_dtf
placed = now() - timedelta(hours=1, minutes=20)
est_delivery = placed + timedelta(minutes=preps[1] + 20)
picked_up    = placed + timedelta(minutes=preps[1] + 5)

dtf_items = first_items(rid, "Soup Dumplings", 2) + first_items(rid, "Noodles & Rice", 1)
subtotal = round(sum(it["price"] for it in dtf_items), 2)
svc, tip, total = calc_financials(subtotal, dfees[1])
oid = uid()
sb.table("lupi_orders").insert({
    "id": oid,
    "order_number": order_num(),
    "customer_id": customer_ids[idx],
    "restaurant_id": rid,
    "dasher_id": dasher_ids[2],
    "delivery_address_id": address_ids[idx],
    "payment_method_id": payment_ids[idx],
    "status": "out_for_delivery",
    "subtotal": subtotal,
    "delivery_fee": dfees[1],
    "service_fee": svc,
    "tip": tip,
    "total": total,
    "placed_at": fmt(placed),
    "estimated_pickup_at": fmt(placed + timedelta(minutes=preps[1])),
    "picked_up_at": fmt(picked_up),
    "estimated_delivery_at": fmt(est_delivery),
    # no delivered_at
}).execute()
for it in dtf_items:
    sb.table("lupi_order_items").insert({
        "id": uid(), "order_id": oid, "menu_item_id": it["id"],
        "name": it["name"], "quantity": 1, "unit_price": it["price"],
    }).execute()
orders.append((oid, customer_ids[idx], rid, "order_not_arrived"))

# ── 4. Marcus Johnson — Sweetgreen — STILL PREPARING (pending) ─────────────────
idx = 3
rid = r_sweet
placed = now() - timedelta(minutes=8)
est_delivery = placed + timedelta(minutes=preps[3] + 20)

sweet_items = first_items(rid, "Salads", 2)
subtotal = round(sum(it["price"] for it in sweet_items), 2)
svc, tip, total = calc_financials(subtotal, dfees[3])
oid = uid()
sb.table("lupi_orders").insert({
    "id": oid,
    "order_number": order_num(),
    "customer_id": customer_ids[idx],
    "restaurant_id": rid,
    "dasher_id": dasher_ids[3],
    "delivery_address_id": address_ids[idx],
    "payment_method_id": payment_ids[idx],
    "status": "pending",
    "subtotal": subtotal,
    "delivery_fee": dfees[3],
    "service_fee": svc,
    "tip": tip,
    "total": total,
    "placed_at": fmt(placed),
    "estimated_pickup_at": fmt(placed + timedelta(minutes=preps[3])),
    "estimated_delivery_at": fmt(est_delivery),
}).execute()
for it in sweet_items:
    sb.table("lupi_order_items").insert({
        "id": uid(), "order_id": oid, "menu_item_id": it["id"],
        "name": it["name"], "quantity": 1, "unit_price": it["price"],
    }).execute()
orders.append((oid, customer_ids[idx], rid, None))

# ── 5. Aisha Williams — Halal Guys — CANCELLED (restaurant closed) ──────────────
idx = 4
rid = r_halal
placed = now() - timedelta(hours=2)
cancelled_at = placed + timedelta(minutes=5)

halal_items = first_items(rid, "Platters", 2)
subtotal = round(sum(it["price"] for it in halal_items), 2)
svc, tip, total = calc_financials(subtotal, dfees[4])
oid = uid()
sb.table("lupi_orders").insert({
    "id": oid,
    "order_number": order_num(),
    "customer_id": customer_ids[idx],
    "restaurant_id": rid,
    "dasher_id": None,
    "delivery_address_id": address_ids[idx],
    "payment_method_id": payment_ids[idx],
    "status": "cancelled",
    "subtotal": subtotal,
    "delivery_fee": dfees[4],
    "service_fee": svc,
    "tip": tip,
    "total": total,
    "placed_at": fmt(placed),
    "estimated_pickup_at": fmt(placed + timedelta(minutes=preps[4])),
    "estimated_delivery_at": fmt(placed + timedelta(minutes=preps[4] + 20)),
    "cancelled_at": fmt(cancelled_at),
    "cancellation_reason": "restaurant_closed",
}).execute()
for it in halal_items:
    sb.table("lupi_order_items").insert({
        "id": uid(), "order_id": oid, "menu_item_id": it["id"],
        "name": it["name"], "quantity": 1, "unit_price": it["price"],
    }).execute()
orders.append((oid, customer_ids[idx], rid, None))

# ── 6. Kevin Zhang — Philz Coffee — HAPPY PATH (on time, no issue) ─────────────
idx = 5
rid = r_philz
placed = now() - timedelta(hours=1)
est_delivery = placed + timedelta(minutes=preps[5] + 20)
picked_up    = placed + timedelta(minutes=preps[5] + 1)
delivered    = est_delivery + timedelta(minutes=7)

philz_items = first_items(rid, "Signature Coffees", 2) + first_items(rid, "Food", 1)
subtotal = round(sum(it["price"] for it in philz_items), 2)
svc, tip, total = calc_financials(subtotal, dfees[5])
oid = uid()
sb.table("lupi_orders").insert({
    "id": oid,
    "order_number": order_num(),
    "customer_id": customer_ids[idx],
    "restaurant_id": rid,
    "dasher_id": dasher_ids[4],
    "delivery_address_id": address_ids[idx],
    "payment_method_id": payment_ids[idx],
    "status": "delivered",
    "subtotal": subtotal,
    "delivery_fee": dfees[5],
    "service_fee": svc,
    "tip": tip,
    "total": total,
    "placed_at": fmt(placed),
    "estimated_pickup_at": fmt(placed + timedelta(minutes=preps[5])),
    "picked_up_at": fmt(picked_up),
    "estimated_delivery_at": fmt(est_delivery),
    "delivered_at": fmt(delivered),
}).execute()
for it in philz_items:
    sb.table("lupi_order_items").insert({
        "id": uid(), "order_id": oid, "menu_item_id": it["id"],
        "name": it["name"], "quantity": 1, "unit_price": it["price"],
    }).execute()
orders.append((oid, customer_ids[idx], rid, None))

# ── 7. Sofia Reyes — Curry Up Now — WRONG ITEMS ─────────────────────────────────
idx = 6
rid = r_curry
placed = now() - timedelta(hours=1, minutes=45)
est_delivery = placed + timedelta(minutes=preps[6] + 20)
picked_up    = placed + timedelta(minutes=preps[6] + 4)
delivered    = est_delivery + timedelta(minutes=8)

curry_items = first_items(rid, "Burritos", 2) + first_items(rid, "Appetizers & Sides", 1)
subtotal = round(sum(it["price"] for it in curry_items), 2)
svc, tip, total = calc_financials(subtotal, dfees[6])
oid = uid()
sb.table("lupi_orders").insert({
    "id": oid,
    "order_number": order_num(),
    "customer_id": customer_ids[idx],
    "restaurant_id": rid,
    "dasher_id": dasher_ids[5],
    "delivery_address_id": address_ids[idx],
    "payment_method_id": payment_ids[idx],
    "status": "delivered",
    "subtotal": subtotal,
    "delivery_fee": dfees[6],
    "service_fee": svc,
    "tip": tip,
    "total": total,
    "placed_at": fmt(placed),
    "estimated_pickup_at": fmt(placed + timedelta(minutes=preps[6])),
    "picked_up_at": fmt(picked_up),
    "estimated_delivery_at": fmt(est_delivery),
    "delivered_at": fmt(delivered),
    "special_instructions": "No onions please on the paneer burrito",
}).execute()
for it in curry_items:
    sb.table("lupi_order_items").insert({
        "id": uid(), "order_id": oid, "menu_item_id": it["id"],
        "name": it["name"], "quantity": 1, "unit_price": it["price"],
    }).execute()
orders.append((oid, customer_ids[idx], rid, "wrong_items"))

# ── 8. Eli Cohen — Mendocino Farms — FOOD QUALITY COMPLAINT ────────────────────
idx = 7
rid = r_mendo
placed = now() - timedelta(hours=1, minutes=30)
est_delivery = placed + timedelta(minutes=preps[7] + 20)
picked_up    = placed + timedelta(minutes=preps[7] + 2)
delivered    = est_delivery + timedelta(minutes=5)

mendo_items = first_items(rid, "Signature Sandwiches", 2) + first_items(rid, "Soups & Sides", 1)
subtotal = round(sum(it["price"] for it in mendo_items), 2)
svc, tip, total = calc_financials(subtotal, dfees[7])
oid = uid()
sb.table("lupi_orders").insert({
    "id": oid,
    "order_number": order_num(),
    "customer_id": customer_ids[idx],
    "restaurant_id": rid,
    "dasher_id": dasher_ids[0],
    "delivery_address_id": address_ids[idx],
    "payment_method_id": payment_ids[idx],
    "status": "delivered",
    "subtotal": subtotal,
    "delivery_fee": dfees[7],
    "service_fee": svc,
    "tip": tip,
    "total": total,
    "placed_at": fmt(placed),
    "estimated_pickup_at": fmt(placed + timedelta(minutes=preps[7])),
    "picked_up_at": fmt(picked_up),
    "estimated_delivery_at": fmt(est_delivery),
    "delivered_at": fmt(delivered),
}).execute()
for it in mendo_items:
    sb.table("lupi_order_items").insert({
        "id": uid(), "order_id": oid, "menu_item_id": it["id"],
        "name": it["name"], "quantity": 1, "unit_price": it["price"],
    }).execute()
orders.append((oid, customer_ids[idx], rid, "food_quality"))

# ── Promotions ─────────────────────────────────────────────────────────────────
print("[LUPI] Seeding promotions...")

promos = [
    ("LUPI10",    "percent_off", 10.00, 15.00),
    ("WELCOME5",  "flat_off",     5.00, 10.00),
    ("DASHPASS15","percent_off", 15.00, 20.00),
    ("FREESHIP",  "free_delivery",0.00,  0.00),
]
for code, ptype, value, min_order in promos:
    sb.table("lupi_promotions").insert({
        "id": uid(),
        "code": code,
        "type": ptype,
        "value": value,
        "min_order": min_order,
        "expires_at": fmt(now() + timedelta(days=30)),
    }).execute()

# ── Summary ────────────────────────────────────────────────────────────────────
print()
print("[LUPI] Database seeded successfully")
print("[LUPI] 8 customers | 6 dashers | 8 restaurants | 8 orders")
print("[LUPI] ")
print("[LUPI] DEMO SCENARIOS:")
print("[LUPI] +14155550101 Maya Patel     → Late delivery (Chipotle, 50min late)")
print("[LUPI] +14155550102 Jordan Rivera  → Missing items (Shake Shack)")
print("[LUPI] +14155550103 Priya Sharma   → Order never arrived (Din Tai Fung, out for delivery)")
print("[LUPI] +14155550104 Marcus Johnson → Order still preparing (Sweetgreen)")
print("[LUPI] +14155550105 Aisha Williams → Restaurant cancelled order (Halal Guys)")
print("[LUPI] +14155550106 Kevin Zhang    → Happy path, no issue (Philz Coffee)")
print("[LUPI] +14155550107 Sofia Reyes    → Wrong items delivered (Curry Up Now)")
print("[LUPI] +14155550108 Eli Cohen      → Food quality complaint (Mendocino Farms)")
