"use strict";

const $app = document.getElementById("app");
const $modalRoot = document.getElementById("modal-root");

const S = {
  me: null,
  view: null,
  menu: [],
  search: "",
  cat: "All",
  sort: "default",
  selectedDate: getTodayStr(),
  slots: [],
  cart: {},
  orders: [],
  stats: null,
  mode: "login",
  timer: null,
  qrOpen: false,
  confirmOrder: null,
  editingItem: null,
  staffDateFilter: "all",
  staffStatusFilter: "all",
};

const STATUS_LABELS = {
  placed: "Pending",
  accepted: "Accepted",
  preparing: "Preparing",
  ready: "Ready for Pickup",
  completed: "Completed",
  collected: "Completed",
  cancelled: "Cancelled",
};

const NEXT_STATUS = {
  placed: ["accepted", "Accept Order"],
  accepted: ["preparing", "Start Preparing"],
  preparing: ["ready", "Mark Ready"],
  ready: ["completed", "Mark Completed"],
};

// Safe DOM builder
function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "class") e.className = v;
    else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  kids.flat(2).forEach(c => {
    if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  });
  return e;
}

async function api(path, method = "GET", body) {
  const r = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || "Something went wrong. Please try again.");
  return d;
}

let toastTimer;
function toast(msg, bad = false) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "show" + (bad ? " bad" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = ""), 3200);
}

const rs = n => "₹" + Number(n).toLocaleString("en-IN");
const guard = fn => async (...a) => {
  try {
    await fn(...a);
  } catch (e) {
    toast(e.message, true);
  }
};

function getTodayStr() {
  // Use LOCAL date, not UTC (toISOString gives UTC which can be a different day in IST/+5:30)
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getRelativeDateStr(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDateDisplay(dateStr) {
  if (!dateStr) return "";
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  const today = getTodayStr();
  const tomorrow = getRelativeDateStr(1);
  const opts = { weekday: "short", day: "numeric", month: "short" };
  const formatted = dt.toLocaleDateString("en-IN", opts);
  if (dateStr === today) return `Today (${formatted})`;
  if (dateStr === tomorrow) return `Tomorrow (${formatted})`;
  return formatted;
}

// Local and category-specific fallback image SVGs
const FALLBACK_FOOD_IMG = "/static/images/fallback.svg";
const CATEGORY_FALLBACK_IMGS = {
  "Breakfast": "/static/images/breakfast.svg",
  "Lunch": "/static/images/lunch.svg",
  "Snacks": "/static/images/snacks.svg",
  "Fast Food": "/static/images/fastfood.svg",
  "Beverages": "/static/images/beverages.svg",
};

function getFallbackImage(category) {
  return CATEGORY_FALLBACK_IMGS[category] || FALLBACK_FOOD_IMG;
}

// ---------- Shell & Navigation ----------
function shell(content) {
  const isStaff = S.me.role === "staff";
  const tabs = isStaff
    ? [["queue", "Order Queue"], ["items", "Menu & Stock"]]
    : [["menu", "Browse Menu"], ["orders", "My Orders"]];

  const cartCount = Object.values(S.cart).reduce((a, b) => a + b, 0);

  return h("div", {},
    h("header", { class: "top" },
      h("div", { class: "brand", onclick: () => go(isStaff ? "queue" : "menu") },
        h("span", { class: "emoji" }, "🍛"),
        h("span", {}, "Smart "),
        h("b", {}, "Canteen")
      ),
      h("nav", { class: "tabs" },
        tabs.map(([v, label]) =>
          h("button", {
            "aria-current": S.view === v ? "page" : null,
            onclick: () => go(v)
          }, label)
        )
      ),
      h("div", { class: "top-actions" },
        h("button", {
          class: "btn-qr-nav",
          title: "View Canteen QR Code",
          onclick: () => { S.qrOpen = true; render(); }
        }, "📱 Canteen QR"),
        h("div", { class: "who" },
          h("span", {}, S.me.name),
          h("span", { class: "user-badge" }, S.me.role),
          h("button", {
            class: "logout-btn",
            title: "Sign Out",
            onclick: guard(async () => {
              await api("/logout", "POST");
              clearInterval(S.timer);
              S.me = null;
              S.cart = {};
              render();
            })
          }, "Log out")
        )
      )
    ),
    h("main", {}, content),
    renderModals()
  );
}

function render() {
  $app.replaceChildren();
  if (!S.me) return $app.append(authView());
  const views = { menu: menuView, orders: ordersView, queue: queueView, items: itemsView };
  $app.append(shell(views[S.view] ? views[S.view]() : h("div", {}, "Page not found")));
}

async function go(view) {
  S.view = view;
  clearInterval(S.timer);
  try {
    if (view === "menu") {
      await loadMenuAndSlots();
    } else if (view === "orders") {
      S.orders = await api("/orders");
      S.timer = setInterval(pollOrders, 6000);
    } else if (view === "queue") {
      await loadStaffQueue();
      S.timer = setInterval(pollOrders, 6000);
    } else if (view === "items") {
      S.menu = await api("/menu?all=1");
    }
  } catch (e) {
    toast(e.message, true);
  }
  render();
}

async function loadMenuAndSlots() {
  const [menuData, slotData] = await Promise.all([
    api("/menu"),
    api(`/slots?date=${S.selectedDate}`),
  ]);
  S.menu = menuData;
  S.slots = slotData;
}

async function loadStaffQueue() {
  // BUG 2 FIX: ordersUrl must be a path suffix only — api() already prepends "/api".
  // Previously was "/api/orders" which became "/api/api/orders" → 404 → empty dashboard.
  let ordersUrl = "/orders";
  if (S.staffDateFilter === "all") {
    ordersUrl += "?all=1";
  } else if (S.staffDateFilter === "tomorrow") {
    ordersUrl += `?date=${getRelativeDateStr(1)}`;
  } else {
    ordersUrl += `?date=${getTodayStr()}`;
  }
  const statsDateParam = S.staffDateFilter === "tomorrow" ? getRelativeDateStr(1) : getTodayStr();
  const [ordersData, statsData] = await Promise.all([
    api(ordersUrl),
    api(`/stats?date=${statsDateParam}`),
  ]);
  S.orders = ordersData;
  S.stats = statsData;
}

async function pollOrders() {
  try {
    if (S.view === "orders") {
      S.orders = await api("/orders");
      render();
    } else if (S.view === "queue") {
      await loadStaffQueue();
      render();
    }
  } catch (e) {
    // keep current view on temporary network drop
  }
}

// ---------- Auth View ----------
function authView() {
  const reg = S.mode === "register";
  const errBox = h("div", { class: "err", style: "display:none" });

  const f = {
    name: h("input", { id: "name", placeholder: "Your Full Name", autocomplete: "name" }),
    email: h("input", { id: "email", type: "email", placeholder: "student@canteen.local", autocomplete: "email" }),
    pw: h("input", { id: "pw", type: "password", placeholder: "••••••••", autocomplete: reg ? "new-password" : "current-password" }),
  };

  const submit = async () => {
    errBox.style.display = "none";
    try {
      S.me = await api(reg ? "/register" : "/login", "POST", {
        name: f.name.value,
        email: f.email.value,
        password: f.pw.value,
      });
      await go(S.me.role === "staff" ? "queue" : "menu");
    } catch (e) {
      errBox.textContent = e.message;
      errBox.style.display = "block";
    }
  };

  // Allow pressing Enter in password input
  f.pw.addEventListener("keydown", e => { if (e.key === "Enter") submit(); });

  return h("div", { class: "auth" },
    h("div", { style: "text-align:center;margin-bottom:1.2rem" },
      h("span", { style: "font-size:3rem" }, "🍛"),
      h("h1", {}, reg ? "Join Smart Canteen" : "Welcome Back"),
      h("p", { class: "subtitle" }, reg ? "Create your student account to order delicious meals" : "Sign in to order food or manage canteen orders")
    ),
    reg && [h("label", { for: "name" }, "Full Name"), f.name],
    h("label", { for: "email" }, "Email Address"), f.email,
    h("label", { for: "pw" }, "Password"), f.pw,
    reg && h("div", { class: "hint" }, "Minimum 6 characters."),
    errBox,
    h("button", { class: "btn alt", onclick: submit }, reg ? "Create Account & Order" : "Log In"),
    h("button", {
      class: "switch",
      onclick: () => { S.mode = reg ? "login" : "register"; render(); }
    }, reg ? "Already have an account? Sign In" : "New here? Create student account"),
    !reg && h("div", { class: "hint", style: "margin-top:1.5rem;text-align:center;border-top:1px solid var(--line);padding-top:1rem" },
      "Staff Login: staff@canteen.local / staff123")
  );
}

// ---------- Student: Menu + Search + Filter + Cart ----------

// BUG 1 FIX: updateMenuGrid() surgically replaces only the food-grid/empty-results
// container without touching the search <input> or anything else.  This keeps the
// browser's focus (and cursor position) on the search box so the user can type full
// words without losing input focus after every character.
function updateMenuGrid() {
  const grid = document.getElementById("menu-food-grid");
  if (!grid) return; // menuView not mounted yet — full render will handle it

  const categories = ["All", "Breakfast", "Lunch", "Snacks", "Fast Food", "Beverages"];
  let shown = S.menu.filter(item => {
    if (S.cat !== "All" && item.category !== S.cat) return false;
    if (S.search) {
      const q = S.search.toLowerCase();
      if (!(item.name || "").toLowerCase().includes(q) &&
          !(item.description || "").toLowerCase().includes(q)) return false;
    }
    return true;
  });

  if (S.sort === "price_asc") shown.sort((a, b) => a.price - b.price);
  else if (S.sort === "price_desc") shown.sort((a, b) => b.price - a.price);
  else if (S.sort === "name_asc") shown.sort((a, b) => a.name.localeCompare(b.name));

  const setQty = (id, delta) => {
    const cur = S.cart[id] || 0;
    const targetItem = S.menu.find(m => m.id === id);
    const maxStock = targetItem ? targetItem.stock : 10;
    const nextVal = Math.max(0, Math.min(Math.min(10, maxStock), cur + delta));
    if (nextVal > 0) S.cart[id] = nextVal; else delete S.cart[id];
    // Only update the grid (not the full page) so cart panel re-renders too
    render();
  };

  let newContent;
  if (shown.length) {
    newContent = h("div", { class: "grid" }, shown.map(item => foodCard(item, setQty)));
  } else {
    newContent = h("div", { class: "empty-results" },
      h("div", { class: "icon" }, "🔍"),
      h("h3", {}, "No food items found"),
      h("p", {}, `We couldn't find anything matching "${S.search || S.cat}". Try a different keyword or category.`),
      h("button", {
        class: "btn sm",
        onclick: () => { S.search = ""; S.cat = "All"; render(); }
      }, "Clear Search & Filters")
    );
  }

  grid.replaceChildren(newContent);
}

function menuView() {
  const categories = ["All", "Breakfast", "Lunch", "Snacks", "Fast Food", "Beverages"];

  // Filter items
  let shown = S.menu.filter(item => {
    if (S.cat !== "All" && item.category !== S.cat) return false;
    if (S.search) {
      const q = S.search.toLowerCase();
      const matchName = (item.name || "").toLowerCase().includes(q);
      const matchDesc = (item.description || "").toLowerCase().includes(q);
      if (!matchName && !matchDesc) return false;
    }
    return true;
  });

  // Sort items
  if (S.sort === "price_asc") {
    shown.sort((a, b) => a.price - b.price);
  } else if (S.sort === "price_desc") {
    shown.sort((a, b) => b.price - a.price);
  } else if (S.sort === "name_asc") {
    shown.sort((a, b) => a.name.localeCompare(b.name));
  }

  const setQty = (id, delta) => {
    const cur = S.cart[id] || 0;
    const targetItem = S.menu.find(m => m.id === id);
    const maxStock = targetItem ? targetItem.stock : 10;
    const nextVal = Math.max(0, Math.min(Math.min(10, maxStock), cur + delta));
    if (nextVal > 0) {
      S.cart[id] = nextVal;
    } else {
      delete S.cart[id];
    }
    render();
  };

  const totalCartItems = Object.values(S.cart).reduce((a, b) => a + b, 0);
  const totalCartAmount = Object.entries(S.cart).reduce((sum, [id, q]) => {
    const it = S.menu.find(m => m.id == id);
    return sum + (it ? it.price * q : 0);
  }, 0);

  return h("div", {},
    h("h1", {}, "Campus Canteen Menu"),
    h("p", { class: "subtitle" }, "Freshly prepared, authentic Indian canteen favorites with rapid slot pickup."),
    
    // Search, Filter & Sort Toolbar
    h("div", { class: "toolbar" },
      h("div", { class: "search-sort-bar" },
        h("div", { class: "search-input-wrap" },
          h("svg", { width: "18", height: "18", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2" },
            h("circle", { cx: "11", cy: "11", r: "8" }),
            h("line", { x1: "21", y1: "21", x2: "16.65", y2: "16.65" })
          ),
          h("input", {
            placeholder: "Search food by name or keywords...",
            value: S.search,
            oninput: e => {
              // BUG 1 FIX: update S.search and re-filter the grid WITHOUT calling
              // render() — that would destroy the <input> and lose keyboard focus.
              S.search = e.target.value;
              updateMenuGrid();
            }
          }),
          S.search && h("button", {
            class: "search-clear-btn",
            onclick: () => { S.search = ""; render(); }
          }, "×")
        ),
        h("div", { class: "sort-select-wrap" },
          h("select", {
            value: S.sort,
            onchange: e => { S.sort = e.target.value; render(); }
          },
            h("option", { value: "default" }, "Sort: Recommended"),
            h("option", { value: "price_asc" }, "Price: Low to High"),
            h("option", { value: "price_desc" }, "Price: High to Low"),
            h("option", { value: "name_asc" }, "Name: A to Z")
          )
        )
      ),
      h("div", { class: "chips" },
        categories.map(c =>
          h("button", {
            "aria-pressed": S.cat === c,
            onclick: () => { S.cat = c; render(); }
          }, c)
        )
      )
    ),

    // Menu Grid + Sticky Cart
    h("div", { class: "layout" },
      h("div", { id: "menu-food-grid" },
        shown.length ? h("div", { class: "grid" }, shown.map(item => foodCard(item, setQty)))
          : h("div", { class: "empty-results" },
              h("div", { class: "icon" }, "🔍"),
              h("h3", {}, "No food items found"),
              h("p", {}, `We couldn't find anything matching "${S.search || S.cat}". Try a different keyword or category.`),
              h("button", {
                class: "btn sm",
                onclick: () => { S.search = ""; S.cat = "All"; render(); }
              }, "Clear Search & Filters")
            )
      ),
      cartPanel(setQty)
    ),

    // Mobile bottom drawer trigger button
    totalCartItems > 0 && h("div", {
      class: "mobile-cart-bar has-items",
      onclick: () => {
        const el = document.querySelector(".cart-panel");
        if (el) el.scrollIntoView({ behavior: "smooth" });
      }
    },
      h("span", {}, `🛒 ${totalCartItems} item${totalCartItems > 1 ? "s" : ""} in cart`),
      h("b", {}, `${rs(totalCartAmount)} · View Cart →`)
    )
  );
}

function foodCard(item, setQty) {
  const q = S.cart[item.id] || 0;
  const isSoldOut = item.stock <= 0 || !item.available;
  const isLowStock = !isSoldOut && item.stock <= 5;
  const fallbackSrc = getFallbackImage(item.category);

  return h("article", { class: "item-card" },
    h("div", { class: "item-img-wrap" },
      h("img", {
        src: item.image || fallbackSrc,
        alt: item.name,
        loading: "lazy",
        onerror: (e) => {
          if (!e.target.dataset.hasFallenBack) {
            e.target.dataset.hasFallenBack = "1";
            e.target.onerror = () => {
              e.target.onerror = null;
              e.target.src = FALLBACK_FOOD_IMG;
            };
            e.target.src = fallbackSrc;
          }
        }
      }),
      h("span", { class: "item-badge-cat" }, item.category),
      h("span", { class: "veg-icon", title: "Vegetarian Food" })
    ),
    h("div", { class: "item-body" },
      h("h3", { class: "item-title" }, item.name),
      h("p", { class: "item-desc" }, item.description || "Fresh & tasty canteen special."),
      h("div", { class: "item-stock-row" },
        isSoldOut
          ? h("span", { class: "stock-pill out" }, "Sold Out")
          : isLowStock
            ? h("span", { class: "stock-pill low" }, `Only ${item.stock} left!`)
            : h("span", { class: "stock-pill in" }, "In Stock")
      ),
      h("div", { class: "item-footer" },
        h("span", { class: "item-price" }, rs(item.price)),
        isSoldOut
          ? h("button", { class: "btn sm", disabled: true }, "Sold Out")
          : q > 0
            ? h("div", { class: "stepper" },
                h("button", {
                  "aria-label": "Decrease " + item.name,
                  onclick: () => setQty(item.id, -1)
                }, "−"),
                h("span", { class: "qty" }, q),
                h("button", {
                  "aria-label": "Increase " + item.name,
                  disabled: q >= item.stock || q >= 10,
                  onclick: () => setQty(item.id, 1)
                }, "+")
              )
            : h("button", {
                class: "btn sm alt",
                onclick: () => setQty(item.id, 1)
              }, "+ Add")
      )
    )
  );
}

// ---------- Cart Panel with Future Date & Slot Picker ----------
function cartPanel(setQty) {
  const lines = Object.entries(S.cart)
    .map(([id, q]) => ({ it: S.menu.find(m => m.id == id), q }))
    .filter(l => l.it);

  const total = lines.reduce((s, l) => s + l.it.price * l.q, 0);

  // Date options: Today, Tomorrow, and Next 2 days
  const dateOptions = [0, 1, 2, 3].map(offset => {
    const val = getRelativeDateStr(offset);
    return { val, label: formatDateDisplay(val) };
  });

  const now = new Date();
  const currentHHMM = String(now.getHours()).padStart(2, "0") + ":" + String(now.getMinutes()).padStart(2, "0");
  const isToday = S.selectedDate === getTodayStr();

  // Filter slots if today: only future slots
  const availableSlots = S.slots.filter(s => {
    if (isToday) return s.slot > currentHHMM;
    return true;
  });

  const slotSelect = h("select", { id: "slot-picker" },
    h("option", { value: "" }, availableSlots.length ? "Choose pickup slot" : "No slots left for selected date"),
    availableSlots.map(s => {
      const free = s.capacity - s.used;
      const full = free <= 0;
      return h("option", {
        value: s.slot,
        disabled: full
      }, `${s.slot} ${full ? "(FULL)" : `(${free} slot${free > 1 ? "s" : ""} free)`}`);
    })
  );

  const onDateChange = async (newDate) => {
    S.selectedDate = newDate;
    try {
      S.slots = await api(`/slots?date=${newDate}`);
    } catch (e) {
      toast("Error fetching slots for selected date.", true);
    }
    render();
  };

  const placeOrder = guard(async () => {
    const slot = slotSelect.value;
    if (!slot) {
      toast("Please select a pickup time slot.", true);
      return;
    }
    const orderData = await api("/orders", "POST", {
      date: S.selectedDate,
      slot: slot,
      items: lines.map(l => ({ item_id: l.it.id, qty: l.q })),
    });

    S.cart = {};
    S.confirmOrder = orderData;
    render();
  });

  return h("aside", { class: "cart-panel" },
    h("h2", {},
      h("span", {}, "Your Cart"),
      lines.length > 0 && h("span", { class: "cart-badge" }, `${lines.reduce((a, b) => a + b.q, 0)} items`)
    ),

    lines.length
      ? h("div", { class: "cart-items" },
          lines.map(l =>
            h("div", { class: "cart-line" },
              h("div", { class: "cart-line-info" },
                h("div", { class: "cart-line-name" }, l.it.name),
                h("div", { class: "cart-line-price" }, `${rs(l.it.price)} each`)
              ),
              h("div", { class: "stepper" },
                h("button", { onclick: () => setQty(l.it.id, -1) }, "−"),
                h("span", { class: "qty" }, l.q),
                h("button", {
                  disabled: l.q >= l.it.stock || l.q >= 10,
                  onclick: () => setQty(l.it.id, 1)
                }, "+")
              ),
              h("span", { class: "cart-line-subtotal" }, rs(l.q * l.it.price)),
              h("button", {
                class: "cart-del-btn",
                title: "Remove item",
                onclick: () => setQty(l.it.id, -l.q)
              }, "🗑")
            )
          )
        )
      : h("div", { class: "empty", style: "text-align:center;padding:2rem 0" },
          h("div", { style: "font-size:2.2rem;margin-bottom:0.4rem" }, "🛒"),
          h("p", { style: "color:var(--muted)" }, "Your cart is empty."),
          h("small", { class: "hint" }, "Click '+ Add' on any menu item.")
        ),

    lines.length > 0 && [
      h("div", { class: "cart-total-box" },
        h("span", {}, "Total Amount:"),
        h("span", {}, rs(total))
      ),

      h("div", { class: "cart-slot-section" },
        h("label", { for: "pickup-date" }, "1. Select Pickup Date:"),
        h("select", {
          id: "pickup-date",
          value: S.selectedDate,
          onchange: e => onDateChange(e.target.value)
        },
          dateOptions.map(opt =>
            h("option", { value: opt.val, selected: opt.val === S.selectedDate }, opt.label)
          )
        ),

        h("label", { for: "slot-picker" }, "2. Select Pickup Time Slot:"),
        slotSelect
      ),

      h("div", { class: "payment-note" },
        h("span", { style: "font-size:1.1rem" }, "💵"),
        h("span", {}, "Payment Method: Pay at Counter when collecting.")
      ),

      h("button", {
        class: "btn alt",
        style: "width:100%;margin-top:1rem;padding:0.75rem",
        onclick: placeOrder
      }, "Confirm & Place Order")
    ]
  );
}

// ---------- Tickets View (Student & Staff) ----------
function ticketCard(order, isStaff = false) {
  // BUG 3 FIX: updateStatus now calls loadStaffQueue()+render() directly instead of
  // pollOrders(). pollOrders() silently swallowed errors in its catch block, so when the
  // follow-up dashboard refresh failed (due to Bug 2 double-/api prefix) the Accept button
  // appeared to do nothing. Now errors surface as toast messages.
  const updateStatus = async (newStatus) => {
    try {
      await api(`/orders/${order.id}/status`, "POST", { status: newStatus });
      if (isStaff) {
        await loadStaffQueue();
      } else {
        S.orders = await api("/orders");
      }
      render();
      toast(`Order status updated to ${newStatus}.`);
    } catch (e) {
      toast(e.message, true);
    }
  };

  const togglePayment = guard(async () => {
    const nextPay = order.payment_status === "paid" ? "unpaid" : "paid";
    await api(`/orders/${order.id}/payment`, "POST", { payment_status: nextPay });
    toast(`Payment marked as ${nextPay.toUpperCase()}.`);
    await pollOrders();
  });

  const nextStep = NEXT_STATUS[order.status];
  const isReady = order.status === "ready";
  const isPaid = order.payment_status === "paid";

  return h("article", { class: `ticket ${isReady ? "ready" : ""}` },
    h("div", { class: "ticket-tok" },
      h("small", {}, "TOKEN"),
      h("b", {}, order.token),
      h("small", { style: "margin-top:0.3rem" }, order.slot)
    ),
    h("div", { class: "ticket-body" },
      h("div", { class: "ticket-header" },
        h("div", { class: "ticket-badges" },
          h("span", { class: `badge s-${order.status}` }, STATUS_LABELS[order.status] || order.status),
          h("span", { class: `badge p-${order.payment_status}` }, isPaid ? "✓ Paid" : "Unpaid (Counter)")
        ),
        h("span", { class: "hint" }, formatDateDisplay(order.order_date))
      ),

      isStaff && h("div", { style: "font-size:0.92rem;margin-top:0.2rem" },
        h("strong", {}, order.customer || "Student"),
        order.customer_email && h("span", { class: "hint" }, ` (${order.customer_email})`)
      ),

      h("ul", { class: "ticket-items" },
        order.items.map(item =>
          h("li", {}, `${item.qty} × ${item.name} (${rs(item.price * item.qty)})`)
        )
      ),

      h("div", { class: "ticket-footer" },
        h("div", {},
          h("span", { style: "font-size:0.85rem;color:var(--muted)" }, "Total: "),
          h("strong", { style: "font-size:1.15rem" }, rs(order.total))
        ),
        h("div", { style: "display:flex;gap:0.4rem;align-items:center;flex-wrap:wrap" },
          isStaff && h("button", {
            class: `btn sm ${isPaid ? "danger" : "success"}`,
            title: isPaid ? "Mark as Unpaid" : "Collect payment at counter",
            onclick: togglePayment
          }, isPaid ? "Mark Unpaid" : "✓ Mark Paid"),

          isStaff && nextStep && h("button", {
            class: "btn sm alt",
            onclick: () => updateStatus(nextStep[0])
          }, nextStep[1]),

          !isStaff && order.status === "placed" && h("button", {
            class: "btn sm danger",
            onclick: () => {
              if (confirm("Are you sure you want to cancel this order?")) {
                updateStatus("cancelled");
              }
            }
          }, "Cancel Order")
        )
      )
    )
  );
}

// ---------- Student: Orders View ----------
function ordersView() {
  const readyOrders = S.orders.filter(o => o.status === "ready");

  return h("div", {},
    h("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem;margin-bottom:1rem" },
      h("div", {},
        h("h1", {}, "My Food Orders"),
        h("p", { class: "subtitle", style: "margin-bottom:0" }, "Track live order status, pickup tokens, and payment receipts.")
      ),
      h("button", {
        class: "btn sm",
        onclick: guard(async () => { S.orders = await api("/orders"); render(); toast("Orders refreshed."); })
      }, "🔄 Refresh")
    ),

    readyOrders.length > 0 && h("div", {
      class: "warn",
      style: "background:#dcfce7;border:1px solid #86efac;color:#14532d;padding:0.8rem 1.2rem;border-radius:10px;margin-bottom:1.5rem;font-weight:600;display:flex;align-items:center;gap:0.6rem"
    },
      h("span", { style: "font-size:1.4rem" }, "🎉"),
      h("span", {}, `${readyOrders.length} order${readyOrders.length > 1 ? "s are" : " is"} READY for pickup! Please proceed to the canteen counter with your token number.`)
    ),

    S.orders.length
      ? h("div", { class: "tickets-grid" }, S.orders.map(o => ticketCard(o, false)))
      : h("div", { class: "empty-results", style: "max-width:500px;margin:3rem auto" },
          h("div", { class: "icon" }, "📋"),
          h("h3", {}, "No orders placed yet"),
          h("p", {}, "Browse our fresh Indian canteen menu and place your first order!"),
          h("button", { class: "btn alt", onclick: () => go("menu") }, "Explore Food Menu")
        ),

    h("p", { class: "hint", style: "text-align:center;margin-top:2rem" }, "This dashboard automatically refreshes order statuses every 6 seconds.")
  );
}

// ---------- Staff: Queue & Live Dashboard ----------
function queueView() {
  const st = S.stats || {};

  // Filter orders by status
  let filteredOrders = S.orders;
  if (S.staffStatusFilter !== "all") {
    filteredOrders = filteredOrders.filter(o => o.status === S.staffStatusFilter);
  }

  const statusFilterTabs = [
    ["all", `All (${S.orders.length})`],
    ["placed", `Pending (${S.orders.filter(o => o.status === "placed").length})`],
    ["accepted", `Accepted (${S.orders.filter(o => o.status === "accepted").length})`],
    ["preparing", `Preparing (${S.orders.filter(o => o.status === "preparing").length})`],
    ["ready", `Ready (${S.orders.filter(o => o.status === "ready").length})`],
    ["completed", `Completed (${S.orders.filter(o => o.status === "completed" || o.status === "collected").length})`],
  ];

  return h("div", {},
    h("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem;margin-bottom:1.2rem" },
      h("div", {},
        h("h1", {}, "Staff Live Orders Dashboard"),
        h("p", { class: "subtitle", style: "margin-bottom:0" }, "Manage kitchen queue, mark counter payments as Paid, and update food prep stages.")
      ),
      h("div", { style: "display:flex;gap:0.5rem" },
        h("button", {
          class: `btn sm ${S.staffDateFilter === "today" ? "alt" : ""}`,
          onclick: () => { S.staffDateFilter = "today"; loadStaffQueue().then(render); }
        }, "Today's Orders"),
        h("button", {
          class: `btn sm ${S.staffDateFilter === "tomorrow" ? "alt" : ""}`,
          onclick: () => { S.staffDateFilter = "tomorrow"; loadStaffQueue().then(render); }
        }, "Tomorrow's Orders"),
        h("button", {
          class: `btn sm ${S.staffDateFilter === "all" ? "alt" : ""}`,
          onclick: () => { S.staffDateFilter = "all"; loadStaffQueue().then(render); }
        }, "All Upcoming")
      )
    ),

    // Stats Cards
    h("div", { class: "stats-row" },
      h("div", { class: "stat-card" },
        h("b", {}, st.orders ?? 0),
        h("span", {}, "Total Orders")
      ),
      h("div", { class: "stat-card" },
        h("b", { style: "color:var(--turmeric-dark)" }, st.pending ?? 0),
        h("span", {}, "In Preparation / Pending")
      ),
      h("div", { class: "stat-card" },
        h("b", { style: "color:var(--leaf)" }, st.paid_orders ?? 0),
        h("span", {}, "Paid at Counter")
      ),
      h("div", { class: "stat-card" },
        h("b", { style: "color:var(--chilli)" }, st.unpaid_orders ?? 0),
        h("span", {}, "Unpaid Counter Orders")
      ),
      h("div", { class: "stat-card" },
        h("b", {}, rs(st.revenue ?? 0)),
        h("span", {}, "Gross Revenue")
      )
    ),

    // Low stock alerts
    st.low_stock && st.low_stock.length > 0 && h("div", {
      class: "warn",
      style: "background:#fef3c7;border:1px solid #fde047;color:#854d0e;padding:0.8rem 1.2rem;border-radius:10px;margin-bottom:1.5rem"
    },
      h("strong", {}, "⚠️ Low Inventory Notice: "),
      st.low_stock.map(item => `${item.name} (${item.stock} left)`).join(", "),
      h("button", {
        class: "btn sm",
        style: "margin-left:1rem",
        onclick: () => go("items")
      }, "Restock Now")
    ),

    // Status Filter Tabs
    h("div", { class: "filter-pills" },
      statusFilterTabs.map(([val, label]) =>
        h("button", {
          "aria-pressed": S.staffStatusFilter === val,
          onclick: () => { S.staffStatusFilter = val; render(); }
        }, label)
      )
    ),

    // Orders Grid
    filteredOrders.length
      ? h("div", { class: "tickets-grid" }, filteredOrders.map(o => ticketCard(o, true)))
      : h("div", { class: "empty-results" },
          h("div", { class: "icon" }, "🍳"),
          h("h3", {}, "No orders in this status"),
          h("p", {}, "Orders placed by students will immediately appear here.")
        )
  );
}

// ---------- Staff: Menu & Stock Management ----------
function itemsView() {
  const categories = ["Breakfast", "Lunch", "Snacks", "Fast Food", "Beverages"];

  const formInputs = {
    name: h("input", { id: "item-name", placeholder: "e.g. Masala Dosa", required: true }),
    category: h("select", { id: "item-cat" },
      categories.map(c => h("option", { value: c }, c))
    ),
    description: h("input", { id: "item-desc", placeholder: "Crisp dosa with potato masala..." }),
    price: h("input", { id: "item-price", type: "number", min: 0, value: 40 }),
    stock: h("input", { id: "item-stock", type: "number", min: 0, value: 30 }),
    image: h("input", { id: "item-img", placeholder: "https://images.unsplash.com/..." }),
  };

  const reloadMenu = async () => {
    S.menu = await api("/menu?all=1");
    render();
  };

  const addItem = guard(async () => {
    await api("/menu", "POST", {
      name: formInputs.name.value,
      category: formInputs.category.value,
      description: formInputs.description.value,
      price: formInputs.price.value,
      stock: formInputs.stock.value,
      image: formInputs.image.value,
    });
    toast("New menu item added!");
    formInputs.name.value = "";
    formInputs.description.value = "";
    formInputs.image.value = "";
    await reloadMenu();
  });

  const updateItem = (id, body) => guard(async () => {
    await api(`/menu/${id}`, "PUT", body);
    toast("Item updated successfully.");
    await reloadMenu();
  });

  const deleteItem = (item) => guard(async () => {
    if (confirm(`Are you sure you want to remove "${item.name}" from the menu?`)) {
      await api(`/menu/${item.id}`, "DELETE");
      toast(`"${item.name}" removed from menu.`);
      await reloadMenu();
    }
  });

  return h("div", {},
    h("h1", {}, "Food Menu & Stock Management"),
    h("p", { class: "subtitle" }, "Add new dishes, update pricing, restock quantities, or toggle availability on student menu."),

    // Add Item Form
    h("div", {
      style: "background:#fff;border:1px solid var(--line);border-radius:14px;padding:1.4rem;margin-bottom:1.8rem;box-shadow:var(--card-shadow)"
    },
      h("h3", { style: "margin-bottom:0.8rem;font-size:1.15rem" }, "+ Add New Canteen Food Item"),
      h("div", {
        style: "display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:0.8rem;align-items:end"
      },
        h("div", {}, h("label", { for: "item-name" }, "Food Name *"), formInputs.name),
        h("div", {}, h("label", { for: "item-cat" }, "Category"), formInputs.category),
        h("div", {}, h("label", { for: "item-price" }, "Price (₹)"), formInputs.price),
        h("div", {}, h("label", { for: "item-stock" }, "Initial Stock"), formInputs.stock),
        h("div", {}, h("label", { for: "item-img" }, "Image URL (optional)"), formInputs.image),
        h("div", { style: "grid-column: 1 / -1" },
          h("label", { for: "item-desc" }, "Description"),
          formInputs.description
        ),
        h("div", { style: "margin-top:0.6rem" },
          h("button", { class: "btn alt", onclick: addItem }, "Save & Add to Menu")
        )
      )
    ),

    // Items Table
    h("div", { class: "staff-table-wrap" },
      h("table", { class: "staff-table" },
        h("thead", {},
          h("tr", {},
            h("th", {}, "Photo"),
            h("th", {}, "Item Name"),
            h("th", {}, "Category"),
            h("th", {}, "Price"),
            h("th", {}, "Stock"),
            h("th", {}, "Availability"),
            h("th", { style: "text-align:right" }, "Actions")
          )
        ),
        h("tbody", {},
          S.menu.map(item => {
            const stockInput = h("input", {
              type: "number",
              min: 0,
              value: item.stock,
              style: "width:70px;padding:0.3rem 0.5rem;display:inline-block;margin-right:0.4rem"
            });

            return h("tr", {},
              h("td", { class: "img-td" },
                (() => {
                  const fallbackSrc = getFallbackImage(item.category);
                  return h("img", {
                    class: "thumb",
                    src: item.image || fallbackSrc,
                    alt: item.name,
                    onerror: (e) => {
                      if (!e.target.dataset.hasFallenBack) {
                        e.target.dataset.hasFallenBack = "1";
                        e.target.onerror = () => {
                          e.target.onerror = null;
                          e.target.src = FALLBACK_FOOD_IMG;
                        };
                        e.target.src = fallbackSrc;
                      }
                    }
                  });
                })()
              ),
              h("td", {},
                h("strong", {}, item.name),
                h("div", { class: "hint", style: "font-size:0.8rem;max-width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" },
                  item.description || "—"
                )
              ),
              h("td", {}, h("span", { class: "badge" }, item.category)),
              h("td", { style: "font-weight:700" }, rs(item.price)),
              h("td", {},
                stockInput,
                h("button", {
                  class: "btn sm",
                  onclick: () => updateItem(item.id, { stock: stockInput.value })()
                }, "Save")
              ),
              h("td", {},
                h("button", {
                  class: `btn sm ${item.available ? "success" : "danger"}`,
                  onclick: () => updateItem(item.id, { available: !item.available })()
                }, item.available ? "✓ Available" : "✗ Hidden")
              ),
              h("td", { style: "text-align:right" },
                h("button", {
                  class: "btn sm",
                  style: "margin-right:0.4rem",
                  onclick: () => { S.editingItem = { ...item }; render(); }
                }, "Edit"),
                h("button", {
                  class: "btn sm danger",
                  onclick: () => deleteItem(item)()
                }, "Delete")
              )
            );
          })
        )
      )
    )
  );
}

// ---------- Modals (QR Code, Order Confirmation, Edit Item) ----------
function renderModals() {
  const kids = [];

  // 1. QR Code Modal
  if (S.qrOpen) {
    const origin = window.location.origin || "http://localhost:5000";
    const qrImg = h("img", {
      src: `/api/canteen-qr?url=${encodeURIComponent(origin + "/")}`,
      alt: "Canteen Menu QR Code",
      style: "width:240px;height:240px;display:block"
    });

    kids.push(h("div", { class: "modal-overlay", onclick: e => { if (e.target.classList.contains("modal-overlay")) { S.qrOpen = false; render(); } } },
      h("div", { class: "modal-content" },
        h("button", { class: "modal-close", onclick: () => { S.qrOpen = false; render(); } }, "×"),
        h("div", { class: "qr-container" },
          h("h2", {}, "📱 Canteen Menu QR Code"),
          h("p", { class: "subtitle" }, "Scan with any smartphone camera to browse the menu and order food."),
          h("div", { class: "qr-svg-wrap" }, qrImg),
          h("div", { class: "qr-url-pill" }, origin + "/"),
          h("div", { style: "display:flex;gap:0.6rem;justify-content:center;flex-wrap:wrap" },
            h("a", {
              href: `/api/canteen-qr?url=${encodeURIComponent(origin + "/")}`,
              download: "smart-canteen-qr.svg",
              class: "btn alt sm"
            }, "⬇ Download QR Code"),
            h("button", {
              class: "btn sm",
              onclick: () => window.print()
            }, "🖨 Print Table Poster"),
            h("button", {
              class: "btn sm",
              onclick: () => {
                navigator.clipboard.writeText(origin + "/");
                toast("Canteen URL copied to clipboard!");
              }
            }, "📋 Copy Link")
          )
        )
      )
    ));
  }

  // 2. Order Confirmation Modal
  if (S.confirmOrder) {
    const o = S.confirmOrder;
    kids.push(h("div", { class: "modal-overlay" },
      h("div", { class: "modal-content" },
        h("div", { style: "text-align:center" },
          h("span", { style: "font-size:3rem" }, "🎉"),
          h("h2", { style: "color:var(--leaf);font-size:1.6rem" }, "Order Placed Successfully!"),
          h("p", { class: "subtitle" }, "Your order is confirmed in the canteen kitchen queue.")
        ),

        h("div", { class: "conf-token-box" },
          h("small", {}, "YOUR PICKUP TOKEN"),
          h("b", {}, `#${o.token}`),
          h("div", { style: "margin-top:0.4rem;font-size:0.95rem;color:#cdd5e3" },
            `Pickup Slot: ${o.slot} (${formatDateDisplay(o.order_date)})`
          )
        ),

        h("div", { class: "conf-details-list" },
          h("div", { class: "conf-row" },
            h("span", {}, "Order ID:"),
            h("strong", {}, `#${o.id}`)
          ),
          h("div", { class: "conf-row" },
            h("span", {}, "Payment Method:"),
            h("strong", {}, "Pay at Counter (Cash / UPI)")
          ),
          h("div", { class: "conf-row" },
            h("span", {}, "Payment Status:"),
            h("span", { class: `badge p-${o.payment_status}` }, o.payment_status === "paid" ? "Paid" : "Unpaid")
          ),
          h("div", { style: "margin:0.6rem 0 0.3rem;font-weight:700" }, "Items Ordered:"),
          h("ul", { style: "padding-left:1.2rem;margin-bottom:0.6rem" },
            o.items.map(i => h("li", {}, `${i.qty} × ${i.name} — ${rs(i.price * i.qty)}`))
          ),
          h("div", { class: "conf-row", style: "border-top:2px solid var(--ink);padding-top:0.6rem;font-size:1.1rem" },
            h("span", { style: "font-weight:800" }, "Total Payable:"),
            h("strong", { style: "color:var(--ink);font-size:1.2rem" }, rs(o.total))
          )
        ),

        h("div", { class: "payment-note" },
          h("span", {}, "ℹ️"),
          h("span", {}, `Please show Token #${o.token} at the canteen counter to collect your meal.`)
        ),

        h("div", { style: "display:flex;gap:0.6rem;margin-top:1.2rem" },
          h("button", {
            class: "btn alt",
            style: "flex:1",
            onclick: () => { S.confirmOrder = null; go("orders"); }
          }, "View in My Orders"),
          h("button", {
            class: "btn",
            style: "flex:1",
            onclick: () => { S.confirmOrder = null; render(); }
          }, "Order More Food")
        )
      )
    ));
  }

  // 3. Edit Item Modal (Staff)
  if (S.editingItem) {
    const it = S.editingItem;
    const ef = {
      name: h("input", { value: it.name, required: true }),
      category: h("select", {},
        ["Breakfast", "Lunch", "Snacks", "Fast Food", "Beverages"].map(c =>
          h("option", { value: c, selected: it.category === c }, c)
        )
      ),
      description: h("textarea", { rows: 3 }, it.description || ""),
      price: h("input", { type: "number", min: 0, value: it.price }),
      stock: h("input", { type: "number", min: 0, value: it.stock }),
      image: h("input", { value: it.image || "" }),
      available: h("input", { type: "checkbox", checked: !!it.available, style: "width:auto;margin-right:0.5rem" }),
    };

    const saveEdit = guard(async () => {
      await api(`/menu/${it.id}`, "PUT", {
        name: ef.name.value,
        category: ef.category.value,
        description: ef.description.value,
        price: ef.price.value,
        stock: ef.stock.value,
        image: ef.image.value,
        available: ef.available.checked ? 1 : 0,
      });
      toast("Item updated successfully!");
      S.editingItem = null;
      S.menu = await api("/menu?all=1");
      render();
    });

    const previewImg = h("img", {
      src: it.image || getFallbackImage(it.category),
      alt: it.name,
      style: "width:100%;height:140px;object-fit:cover;border-radius:10px;margin-bottom:0.8rem;background:#14213d;display:block",
      onerror: (e) => { e.target.onerror = null; e.target.src = FALLBACK_FOOD_IMG; }
    });
    ef.image.addEventListener("input", e => {
      previewImg.src = e.target.value.trim() || getFallbackImage(ef.category.value);
    });

    kids.push(h("div", { class: "modal-overlay", onclick: e => { if (e.target.classList.contains("modal-overlay")) { S.editingItem = null; render(); } } },
      h("div", { class: "modal-content" },
        h("button", { class: "modal-close", onclick: () => { S.editingItem = null; render(); } }, "×"),
        h("h2", {}, `Edit: ${it.name}`),
        h("div", { style: "margin-top:1rem" },
          previewImg,
          h("label", {}, "Food Name"), ef.name,
          h("label", {}, "Category"), ef.category,
          h("label", {}, "Description"), ef.description,
          h("div", { style: "display:grid;grid-template-columns:1fr 1fr;gap:0.8rem" },
            h("div", {}, h("label", {}, "Price (₹)"), ef.price),
            h("div", {}, h("label", {}, "Stock"), ef.stock)
          ),
          h("label", {}, "Image URL"), ef.image,
          h("label", { style: "display:flex;align-items:center;margin-top:1rem;cursor:pointer" },
            ef.available,
            h("span", {}, "Available on student menu")
          ),
          h("div", { style: "display:flex;gap:0.6rem;margin-top:1.4rem" },
            h("button", { class: "btn alt", style: "flex:1", onclick: saveEdit }, "Save Changes"),
            h("button", { class: "btn sm", onclick: () => { S.editingItem = null; render(); } }, "Cancel")
          )
        )
      )
    ));
  }

  return h("div", {}, kids);
}

// ---------- Application Boot ----------
(async function init() {
  try {
    S.me = await api("/me");
  } catch (e) {
    S.me = null;
  }
  if (S.me) {
    await go(S.me.role === "staff" ? "queue" : "menu");
  } else {
    render();
  }
})();
