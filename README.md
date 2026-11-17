# Smart Canteen Ordering System

A full-stack, responsive web application (Flask + SQLite + Vanilla JS) for campus food ordering with pre-scheduled pickup time slots, daily order tokens, live kitchen queue management, and table/counter QR code ordering.

---

## Architecture Overview

```
               ┌────────────────────────────────────────────────────────┐
               │                     Web Browser                        │
               │        (Responsive Single Page App - Vanilla JS)       │
               └──────────┬─────────────────────────────┬───────────────┘
                          │ HTTP REST API               │ QR Code Scan
                          ▼                             ▼
               ┌────────────────────────────────────────────────────────┐
               │                   Python Flask API                     │
               │   • Auth & Session Mgmt      • Menu & Inventory CRUD   │
               │   • Slot Capacity Booking    • Daily Token Engine      │
               │   • Order State Transitions  • Zero-Dep SVG QR Gen     │
               └──────────────────────────┬─────────────────────────────┘
                                          │ PRAGMA foreign_keys = ON
                                          ▼
                               ┌─────────────────────┐
                               │     SQLite DB       │
                               │  (canteen.db)       │
                               └─────────────────────┘
```

- **Frontend**: Clean Vanilla JavaScript (SPA), standard CSS variables, modern responsive flex/grid layouts, mobile sticky cart, no node build steps required.
- **Backend**: Python 3 (Flask), SQLite with foreign keys, atomic transactions (`BEGIN IMMEDIATE`) to prevent race conditions and overselling.
- **QR Code Engine**: Pure Python, zero-dependency SVG QR code generator (`qr_generator.py`) supporting direct mobile scanning, poster printing, and downloads.

---

## Features

### 1. Indian Food Menu (50+ Items)
- **Extensive realistic menu**: Over 50 authentic Indian canteen dishes across **Breakfast**, **Lunch**, **Snacks**, **Fast Food**, and **Beverages**.
- **Rich item details**: High-resolution dish photos, descriptions, realistic Indian prices (₹), category tags, stock levels, and Indian vegetarian markers.
- **Persistent storage**: Stored and managed in SQLite with automatic schema migration.

### 2. Live Search, Filter & Sort
- **Search bar**: Real-time search across food names and descriptions with instant clear (`×`).
- **Category filters**: One-click pills for `All`, `Breakfast`, `Lunch`, `Snacks`, `Fast Food`, and `Beverages`.
- **Price & alphabetical sorting**: "Price: Low to High", "Price: High to Low", and "Name: A to Z".
- **Empty state**: Helpful illustration and suggestion when no search matches are found.

### 3. Order Placement & Token Engine
- **Cart management**: Add items, increase/decrease quantities, or remove items.
- **Future pickup booking**: Select pickup time slots for **Today**, **Tomorrow**, or upcoming dates.
- **Slot capacity enforcement**: 15-minute pickup slots (8:00 AM – 6:00 PM) with live availability indicators (`X slots free` / `FULL`).
- **Unique daily token**: Generates a sequential, prominent order token (`Token #1`, `Token #2`, ...) per pickup date.
- **Order confirmation screen**: Celebratory confirmation modal displaying the token number, order details, pickup date/time, and counter pickup instructions.
- **Payment tracking**: "Pay at Counter" payment method with separate `Unpaid` and `Paid` payment status tracking.

### 4. Canteen QR Code
- **One common QR code**: Pointing to the canteen ordering web application.
- **Accessible anywhere**: "📱 Canteen QR" button in navigation bar.
- **Self-contained**: Generates crisp, printable SVG QR codes with zero third-party dependencies.
- **Staff / Admin poster**: Options to download the SVG or print counter/table posters directly from the browser.

### 5. Staff Dashboard
- **Live order queue**: Grouped and filtered by status: `Pending (Placed)`, `Accepted`, `Preparing`, `Ready for Pickup`, and `Completed`.
- **Status workflow**: Move orders smoothly through preparation stages.
- **Counter payment collection**: One-click `✓ Mark Paid` button to record payments collected at the counter.
- **Real-time business stats**: Total daily orders, pending orders, paid vs. unpaid breakdown, and gross revenue.
- **Menu & stock management**: Staff can add new dishes, edit prices/descriptions/images, restock quantities, or toggle visibility (`Show` / `Hide`).
- **Low inventory alerts**: Automatic warnings when menu items drop to 5 or fewer servings.

---

## Getting Started

### Prerequisites
- Python 3.10+ (tested on Python 3.12 and 3.14)
- `pip`

### Installation & Run

1. Navigate to the project directory:
   ```bash
   cd smart-canteen
   ```

2. (Optional) Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

4. Start the application:
   ```bash
   python app.py
   ```

5. Open your browser:
   - **Student / General Access**: [http://localhost:5000](http://localhost:5000)
   - **Staff Credentials**:
     - Email: `staff@canteen.local`
     - Password: `staff123`

---

## Running Automated Tests

Run the full automated test suite covering authentication, menu seeding, category filtering, search, cart, order placement, token incrementing, future slots, payment tracking, staff dashboard, and QR code generation:

```bash
python -m unittest discover -s tests -v
```

All unit tests run against an isolated in-memory/temporary SQLite database and clean up automatically.

---

## Containerization & CI/CD Manifests

The repository includes configuration files for containerization and automated deployments:

- `Dockerfile`: Single-worker Gunicorn server configuration tailored for SQLite single-writer semantics.
- `docker-compose.yml`: Local multi-container setup with persistent SQLite volume.
- `Jenkinsfile`: Declarative Jenkins pipeline (Unit tests → Docker build → Tagging → Kubernetes apply).
- `k8s/deployment.yaml` & `k8s/service.yaml`: Kubernetes manifests with NodePort service.

> **Note on CI/CD & Kubernetes Status**: The Docker, Jenkins, and Kubernetes configurations are provided as infrastructure templates. They require a configured Docker Hub registry, Jenkins runner, and Kubernetes cluster (e.g. Minikube or Kind) with valid secrets to execute. Local testing with `python app.py` and `python -m unittest discover -s tests -v` is fully validated and operational.

---

## API Reference Summary

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/health` | GET | Public | Health check |
| `/api/register` | POST | Public | Register new student account |
| `/api/login` | POST | Public | Authenticate user (student or staff) |
| `/api/logout` | POST | Public | Clear session |
| `/api/me` | GET | Public | Get currently logged-in user profile |
| `/api/menu` | GET | User | Fetch menu items (supports `?category=`, `?q=`, `?sort=`) |
| `/api/menu` | POST | Staff | Add new food item to menu |
| `/api/menu/<id>` | PUT | Staff | Edit food item details, price, stock, availability |
| `/api/menu/<id>` | DELETE | Staff | Soft-delete food item from menu |
| `/api/slots` | GET | User | Get 15-minute pickup slots & availability for `?date=YYYY-MM-DD` |
| `/api/orders` | POST | Student | Place order with cart items, slot, and optional date |
| `/api/orders` | GET | User | List user's orders (students) or incoming orders (staff) |
| `/api/orders/<id>/status` | POST | User | Update status (`placed` -> `accepted` -> `preparing` -> `ready` -> `completed`, or cancel) |
| `/api/orders/<id>/payment` | POST | Staff | Update payment status (`paid` or `unpaid`) |
| `/api/stats` | GET | Staff | Summary metrics, revenue, and low stock items |
| `/api/canteen-qr` | GET | Public | Returns pure SVG QR code for canteen ordering URL |
| `/api/canteen-qr/info` | GET | Public | Returns JSON with target URL and SVG string |
