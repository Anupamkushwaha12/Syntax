const API_BASE = "http://localhost:8000/api/v1";
const WS_BASE  = "ws://localhost:8000";

// ── Styles used in modal ──────────────────────────────────────────────────────
const INPUT_STYLE = "display:block;width:100%;padding:0.75rem 1rem;margin-bottom:0.75rem;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:12px;color:white;font-size:0.95rem;outline:none;box-sizing:border-box;";
const BTN_STYLE   = "width:100%;padding:0.9rem;background:linear-gradient(135deg,#10b981,#059669);color:white;border:none;border-radius:12px;font-weight:600;font-size:1rem;cursor:pointer;margin-top:0.25rem;";

// ── Token Storage ─────────────────────────────────────────────────────────────
const Auth = {
  getToken:   () => localStorage.getItem("fb_token"),
  getUser:    () => JSON.parse(localStorage.getItem("fb_user") || "null"),
  isLoggedIn: () => !!localStorage.getItem("fb_token"),
  save(data) {
    localStorage.setItem("fb_token", data.access_token);
    localStorage.setItem("fb_refresh", data.refresh_token);
    localStorage.setItem("fb_user", JSON.stringify({ id: data.user_id, role: data.role }));
  },
  clear() {
    ["fb_token","fb_refresh","fb_user"].forEach(k => localStorage.removeItem(k));
  }
};

// ── HTTP Client ───────────────────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = Auth.getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";

  const res = await fetch(API_BASE + path, { ...options, headers });

  if (res.status === 401) { Auth.clear(); return; }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    const msg = Array.isArray(detail) ? detail.map(e => e.msg || JSON.stringify(e)).join(', ') : (detail || res.statusText);
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

// ── API Modules ───────────────────────────────────────────────────────────────
const AuthAPI = {
  register: (data) => apiFetch("/auth/register", { method: "POST", body: JSON.stringify(data) }),
  async login(email, password) {
    const result = await apiFetch("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    Auth.save(result);
    window.dispatchEvent(new CustomEvent("fb:login", { detail: result }));
    return result;
  },
  logout() { Auth.clear(); window.dispatchEvent(new CustomEvent("fb:logout")); }
};

const DonationsAPI = {
  create: (fd) => apiFetch("/donations", { method: "POST", body: fd }),
  list:   (status) => apiFetch("/donations" + (status ? "?status=" + status : "")),
};

const RequestsAPI = {
  create: (data) => apiFetch("/requests", { method: "POST", body: JSON.stringify(data) }),
  list:   (status) => apiFetch("/requests" + (status ? "?status=" + status : "")),
};

const DeliveriesAPI = {
  list:         (status) => apiFetch("/deliveries" + (status ? "?status=" + status : "")),
  get:          (id) => apiFetch("/deliveries/" + id),
  accept:       (id) => apiFetch("/deliveries/" + id + "/accept", { method: "POST" }),
  markPickedUp: (id) => apiFetch("/deliveries/" + id + "/pickup", { method: "POST" }),
  markDelivered:(id) => apiFetch("/deliveries/" + id + "/deliver", { method: "POST" }),
  verifyOTP:    (delivery_id, otp_code) => apiFetch("/deliveries/verify-otp", { method: "POST", body: JSON.stringify({ delivery_id, otp_code }) }),
};

const AnalyticsAPI = {
  summary:      () => apiFetch("/analytics/summary"),
  activityFeed: (limit) => apiFetch("/analytics/activity-feed?limit=" + (limit || 10)),
};

const VolunteerAPI = {
  myDeliveries:   (status) => apiFetch("/volunteers/my-deliveries" + (status ? "?status=" + status : "")),
  updateLocation: (lat, lng) => apiFetch("/volunteers/location", { method: "POST", body: JSON.stringify({ lat, lng }) }),
  stats:          () => apiFetch("/volunteers/stats"),
};

// ── WebSocket ─────────────────────────────────────────────────────────────────
class FoodBridgeSocket {
  constructor() { this._ws = null; this._handlers = {}; this._delay = 3000; }

  connect() {
    const token = Auth.getToken();
    if (!token) return;
    this._ws = new WebSocket(WS_BASE + "/ws?token=" + token);
    this._ws.onopen    = () => { console.log("[FB] WS connected"); this._delay = 3000; };
    this._ws.onmessage = (e) => { try { const d = JSON.parse(e.data); this._emit(d.event, d); this._emit("*", d); } catch(_){} };
    this._ws.onclose   = () => { setTimeout(() => this.connect(), this._delay); this._delay = Math.min(this._delay * 2, 30000); };
  }

  on(event, fn) { (this._handlers[event] = this._handlers[event] || []).push(fn); }
  _emit(event, data) { (this._handlers[event] || []).forEach(fn => fn(data)); }

  ping() { setInterval(() => { if (this._ws && this._ws.readyState === 1) this._ws.send("ping"); }, 30000); }
}
const Socket = new FoodBridgeSocket();

// ── Activity Feed Helper ──────────────────────────────────────────────────────
function addActivityItem(icon, type, message, location, badge, time) {
  const feed = document.getElementById("activityFeed");
  if (!feed) return;

  // Remove empty state if present
  const empty = feed.querySelector(".fb-empty");
  if (empty) empty.remove();

  const badgeClass = badge.toLowerCase().replace(/\s+/g, "-");
  const item = document.createElement("div");
  item.className = "activity-item";
  item.innerHTML =
    '<div class="activity-icon ' + type + '"><i data-lucide="' + icon + '"></i></div>' +
    '<div class="activity-content">' +
      '<div class="activity-message">' + message + '</div>' +
      '<div class="activity-meta">' +
        '<span class="activity-location"><i data-lucide="map-pin"></i> ' + (location || "—") + '</span>' +
        '<span class="activity-time"><i data-lucide="clock"></i> ' + (time || "Just now") + '</span>' +
      '</div>' +
    '</div>' +
    '<span class="activity-badge ' + badgeClass + '">' + badge + '</span>';

  feed.insertBefore(item, feed.firstChild);
  if (window.lucide) lucide.createIcons();
  if (feed.children.length > 4) feed.removeChild(feed.lastChild);
}

// ── Load real data from backend ───────────────────────────────────────────────
async function loadActivityFeed() {
  try {
    const items = await AnalyticsAPI.activityFeed(4);
    if (!items || !items.length) return showEmptyFeed();
    const feed = document.getElementById("activityFeed");
    if (feed) feed.innerHTML = "";
    const typeMap = {
      food_donated:       { icon: "heart",         type: "donate" },
      volunteer_assigned: { icon: "bike",           type: "volunteer" },
      delivery_completed: { icon: "package-check",  type: "delivery" },
      ngo_joined:         { icon: "building-2",     type: "ngo" },
      food_expired:       { icon: "alert-triangle", type: "donate" },
      user_registered:    { icon: "user-plus",      type: "ngo" },
    };
    items.forEach(item => {
      const t = typeMap[item.activity_type] || { icon: "activity", type: "donate" };
      const badge = item.activity_type === "delivery_completed" ? "Completed" : "New";
      addActivityItem(t.icon, t.type, item.message, item.location_name, badge, timeAgo(item.created_at));
    });
  } catch(_) { showEmptyFeed(); }
}

async function loadCounter() {
  try {
    const s = await AnalyticsAPI.summary();
    const el = document.getElementById("mainCounter");
    if (el) animateCounter("mainCounter", s.total_meals_delivered || 0, 1500);
  } catch(_) {}
}

async function loadMapStats() {
  try {
    const s = await AnalyticsAPI.summary();
    const d = document.getElementById("statDistance");
    const e = document.getElementById("statETA");
    const x = document.getElementById("statExpiry");
    if (d) d.textContent = s.active_volunteers + " vol";
    if (e) e.textContent = s.avg_delivery_minutes ? s.avg_delivery_minutes + " min" : "—";
    if (x) x.textContent = s.expired_percentage + "%";
  } catch(_) {}
}

function showEmptyFeed() {
  const feed = document.getElementById("activityFeed");
  if (!feed || feed.children.length > 0) return;
  const div = document.createElement("div");
  div.className = "fb-empty";
  div.style.cssText = "text-align:center;padding:2rem;color:rgba(255,255,255,0.3);font-size:0.9rem;";
  div.innerHTML = "<div style='font-size:2rem;margin-bottom:0.5rem;'>📭</div>No activity yet. Be the first to donate!";
  feed.appendChild(div);
}

// ── Phone formatter ──────────────────────────────────────────────────────────
function formatPhone(input) {
  let v = input.value.replace(/[^\d+]/g, '');
  if (v && !v.startsWith('+')) v = '+91' + v;
  input.value = v;
}

// ── Auth Modal ────────────────────────────────────────────────────────────────
function showAuthModal(action) {
  document.getElementById("fb-auth-modal") && document.getElementById("fb-auth-modal").remove();

  action = action || "";
  const isDonate    = action.toLowerCase().includes("donat");
  const isVolunteer = action.toLowerCase().includes("volunteer");
  const defaultRole = isDonate ? "donor" : isVolunteer ? "volunteer" : "receiver";

  const modal = document.createElement("div");
  modal.id = "fb-auth-modal";
  modal.style.cssText = "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.75);backdrop-filter:blur(8px);";

  modal.innerHTML =
    '<div style="background:#0d0d14;border:1px solid rgba(255,255,255,0.12);border-radius:24px;padding:2.5rem;width:100%;max-width:440px;position:relative;">' +
      '<button id="fb-close" style="position:absolute;top:1rem;right:1.25rem;background:none;border:none;color:rgba(255,255,255,0.5);font-size:1.5rem;cursor:pointer;line-height:1;">✕</button>' +
      '<h2 style="font-family:Space Grotesk,sans-serif;font-size:1.5rem;color:white;margin-bottom:0.4rem;">Join FoodBridge</h2>' +
      '<p style="color:rgba(255,255,255,0.45);font-size:0.88rem;margin-bottom:1.5rem;">' + (action ? 'To "' + action + '", sign in or create an account.' : "Sign in to continue.") + '</p>' +

      '<div style="display:flex;background:rgba(0,0,0,0.4);border-radius:12px;padding:4px;margin-bottom:1.5rem;">' +
        '<button class="fb-tab" data-tab="login"    style="flex:1;padding:0.6rem;border:none;border-radius:10px;cursor:pointer;font-weight:600;font-size:0.9rem;background:linear-gradient(135deg,#10b981,#059669);color:white;">Sign In</button>' +
        '<button class="fb-tab" data-tab="register" style="flex:1;padding:0.6rem;border:none;border-radius:10px;cursor:pointer;font-weight:600;font-size:0.9rem;background:none;color:rgba(255,255,255,0.5);">Register</button>' +
      '</div>' +

      '<form id="fb-login-form">' +
        '<input name="email"    type="email"    placeholder="Email"    required style="' + INPUT_STYLE + '">' +
        '<input name="password" type="password" placeholder="Password" required style="' + INPUT_STYLE + '">' +
        '<button type="submit" style="' + BTN_STYLE + '">Sign In</button>' +
        '<p id="fb-login-err" style="color:#ef4444;font-size:0.85rem;margin-top:0.5rem;display:none;"></p>' +
      '</form>' +

      '<form id="fb-register-form" style="display:none;">' +
        '<input name="name"     type="text"     placeholder="Full Name"         required style="' + INPUT_STYLE + '">' +
        '<input name="email"    type="email"    placeholder="Email"             required style="' + INPUT_STYLE + '">' +
        '<input name="phone"    type="tel"      placeholder="WhatsApp: +91XXXXXXXXXX"           style="' + INPUT_STYLE + '" oninput="formatPhone(this)">' +
        '<input name="password" type="password" placeholder="Password"          required style="' + INPUT_STYLE + '">' +
        '<select name="role" style="' + INPUT_STYLE + '">' +
          '<option value="donor"     ' + (defaultRole==="donor"     ? "selected" : "") + '>🍱 Food Donor</option>' +
          '<option value="receiver"  ' + (defaultRole==="receiver"  ? "selected" : "") + '>🙏 Food Receiver</option>' +
          '<option value="volunteer" ' + (defaultRole==="volunteer" ? "selected" : "") + '>🚴 Volunteer</option>' +
          '<option value="ngo">🏢 NGO</option>' +
        '</select>' +
        '<input name="address" type="text" placeholder="Your City / Address" style="' + INPUT_STYLE + '">' +
        '<button type="submit" style="' + BTN_STYLE + '">Create Account</button>' +
        '<p id="fb-register-err" style="color:#ef4444;font-size:0.85rem;margin-top:0.5rem;display:none;"></p>' +
      '</form>' +
    '</div>';

  document.body.appendChild(modal);

  // Close
  document.getElementById("fb-close").onclick = () => modal.remove();
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };

  // Tab switch
  modal.querySelectorAll(".fb-tab").forEach(tab => {
    tab.onclick = () => {
      modal.querySelectorAll(".fb-tab").forEach(t => { t.style.background = "none"; t.style.color = "rgba(255,255,255,0.5)"; });
      tab.style.background = "linear-gradient(135deg,#10b981,#059669)";
      tab.style.color = "white";
      document.getElementById("fb-login-form").style.display    = tab.dataset.tab === "login" ? "block" : "none";
      document.getElementById("fb-register-form").style.display = tab.dataset.tab === "register" ? "block" : "none";
    };
  });

  // Login
  document.getElementById("fb-login-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const err = document.getElementById("fb-login-err");
    err.style.display = "none";
    try {
      await AuthAPI.login(fd.get("email"), fd.get("password"));
      modal.remove();
      showToast("Welcome back! 👋", "success");
      bootConnected();
    } catch(ex) { err.textContent = ex.message; err.style.display = "block"; }
  };

  // Register
  document.getElementById("fb-register-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const err = document.getElementById("fb-register-err");
    err.style.display = "none";
    try {
      const rawPhone = fd.get("phone");
      const phone = rawPhone ? (rawPhone.startsWith('+') ? rawPhone : '+91' + rawPhone.replace(/\D/g,'')) : null;
      await AuthAPI.register({
        name: fd.get("name"), email: fd.get("email"),
        phone: phone, password: fd.get("password"),
        role: fd.get("role"), address: fd.get("address") || null,
      });
      await AuthAPI.login(fd.get("email"), fd.get("password"));
      modal.remove();
      showToast("Account created! Welcome to FoodBridge 🎉", "success");
      bootConnected();
    } catch(ex) { err.textContent = ex.message; err.style.display = "block"; }
  };
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(message, type) {
  const colors = { success:"#10b981", error:"#ef4444", info:"#3b82f6", warning:"#f59e0b" };
  const t = document.createElement("div");
  t.style.cssText = "position:fixed;bottom:2rem;right:2rem;z-index:99999;background:#0d0d14;border:1px solid " + (colors[type]||colors.info) + ";border-radius:14px;padding:1rem 1.5rem;color:white;font-size:0.95rem;font-weight:500;box-shadow:0 8px 30px rgba(0,0,0,0.5);max-width:360px;";
  t.textContent = message;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

// ── Utility ───────────────────────────────────────────────────────────────────
function timeAgo(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "Just now";
  if (s < 3600) return Math.floor(s/60) + " min ago";
  if (s < 86400) return Math.floor(s/3600) + " hr ago";
  return Math.floor(s/86400) + " days ago";
}

// ── Boot after login ──────────────────────────────────────────────────────────
function bootConnected() {
  Socket.connect();
  Socket.ping();

  // Wire WS events to activity feed
  Socket.on("delivery_completed", (d) => addActivityItem("package-check", "delivery", "Delivery completed by " + (d.volunteer_name || "volunteer"), "Live", "Completed", "Just now"));
  Socket.on("match_created",      (d) => addActivityItem("zap",           "donate",   "Match created — ETA " + d.estimated_minutes + " min",          "Live", "New",       "Just now"));
  Socket.on("food_picked_up",     ()  => addActivityItem("bike",          "volunteer","Volunteer picked up food — en route!",                          "Live", "In Progress","Just now"));

  // Update nav button
  const user = Auth.getUser();
  const cta = document.querySelector(".nav-cta");
  if (cta && user) cta.textContent = user.role.charAt(0).toUpperCase() + user.role.slice(1) + " Dashboard";

  // Load real data
  loadCounter();
  loadActivityFeed();
  loadMapStats();
  setInterval(loadActivityFeed, 30000);
}

// ── Init on page load ─────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Hook all CTA buttons
  document.querySelectorAll(".btn-primary, .btn-secondary, .btn-tertiary, .nav-cta").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const text = btn.textContent.trim().toLowerCase();
      if (!Auth.isLoggedIn()) {
        showAuthModal(btn.textContent.trim());
      } else if (text.includes("donat")) {
        showDonateModal();
      } else if (text.includes("request")) {
        showRequestModal();
      } else if (text.includes("volunteer")) {
        showToast("You are registered as a volunteer! Keep your availability ON.", "info");
      } else {
        showToast("You are logged in as " + (Auth.getUser() && Auth.getUser().role) + " 👤", "info");
      }
    });
  });

  // If already logged in from previous session
  if (Auth.isLoggedIn()) {
    bootConnected();
  } else {
    // Show empty states
    setTimeout(showEmptyFeed, 500);
  }

  window.addEventListener("fb:logout", () => {
    const cta = document.querySelector(".nav-cta");
    if (cta) cta.textContent = "Get Started";
  });
});

// ── Global expose ─────────────────────────────────────────────────────────────
window.FoodBridge = { Auth, AuthAPI, DonationsAPI, RequestsAPI, DeliveriesAPI, AnalyticsAPI, VolunteerAPI, Socket, showAuthModal, showDonateModal, showRequestModal, showToast };

// ── Donate Modal — redirects to donate.html ─────────────────────────────────
function showDonateModal() {
  if (!Auth.isLoggedIn()) {
    alert('Please sign in first before donating. Redirecting to the login modal.');
    if (window.FoodBridge && window.FoodBridge.showAuthModal) {
      window.FoodBridge.showAuthModal('Donate Food Now');
    }
    return;
  }
  window.location.href = 'donate.html';
}

// legacy code below kept for reference
function _unused_showDonateModal() {
  document.getElementById("fb-donate-modal") && document.getElementById("fb-donate-modal").remove();

  const modal = document.createElement("div");
  modal.id = "fb-donate-modal";
  modal.style.cssText = "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.75);backdrop-filter:blur(8px);overflow-y:auto;padding:1rem;";

  modal.innerHTML =
    '<div style="background:#0d0d14;border:1px solid rgba(255,255,255,0.12);border-radius:24px;padding:2.5rem;width:100%;max-width:480px;position:relative;">' +
      '<button id="fb-donate-close" style="position:absolute;top:1rem;right:1.25rem;background:none;border:none;color:rgba(255,255,255,0.5);font-size:1.5rem;cursor:pointer;">✕</button>' +
      '<h2 style="font-family:Space Grotesk,sans-serif;font-size:1.4rem;color:white;margin-bottom:0.3rem;">🍱 Donate Food</h2>' +
      '<p style="color:rgba(255,255,255,0.4);font-size:0.85rem;margin-bottom:1.5rem;">Fill in the details below. Food will be matched to nearby receivers.</p>' +

      '<form id="fb-donate-form">' +

        '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Food Type</label>' +
        '<select name="food_type" required style="' + INPUT_STYLE + '">' +
          '<option value="veg">🥬 Vegetarian</option>' +
          '<option value="non_veg">🍖 Non-Vegetarian</option>' +
        '</select>' +

        '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Category</label>' +
        '<select name="category" required style="' + INPUT_STYLE + '">' +
          '<option value="cooked">🍳 Cooked</option>' +
          '<option value="raw">🥕 Raw</option>' +
          '<option value="packaged">📦 Packaged</option>' +
        '</select>' +

        '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Description</label>' +
        '<input name="description" type="text" placeholder="e.g. Rice, Dal, Roti (50 plates)" style="' + INPUT_STYLE + '">' +

        '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Number of Serves (people)</label>' +
        '<input name="quantity_serves" type="number" min="1" max="10000" placeholder="e.g. 20" required style="' + INPUT_STYLE + '">' +

        '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Food Expiry Time</label>' +
        '<input name="expiry_time" type="datetime-local" required style="' + INPUT_STYLE + '">' +

        '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Pickup Address</label>' +
        '<input name="pickup_address" type="text" placeholder="Full address for pickup" required style="' + INPUT_STYLE + '">' +

        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;">' +
          '<div>' +
            '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Latitude</label>' +
            '<input name="pickup_lat" type="number" step="any" placeholder="e.g. 19.0760" required style="' + INPUT_STYLE + '">' +
          '</div>' +
          '<div>' +
            '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Longitude</label>' +
            '<input name="pickup_lng" type="number" step="any" placeholder="e.g. 72.8777" required style="' + INPUT_STYLE + '">' +
          '</div>' +
        '</div>' +

        '<button type="button" id="fb-use-location" style="width:100%;padding:0.6rem;background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.3);border-radius:10px;color:#10b981;font-size:0.85rem;cursor:pointer;margin-bottom:0.75rem;">📍 Use My Current Location</button>' +

        '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Food Image (optional)</label>' +
        '<input name="image" type="file" accept="image/*" style="' + INPUT_STYLE + 'color:rgba(255,255,255,0.5);">' +

        '<button type="submit" style="' + BTN_STYLE + '">Submit Donation</button>' +
        '<p id="fb-donate-err" style="color:#ef4444;font-size:0.85rem;margin-top:0.5rem;display:none;"></p>' +
        '<p id="fb-donate-ok"  style="color:#10b981;font-size:0.85rem;margin-top:0.5rem;display:none;"></p>' +
      '</form>' +
    '</div>';

  document.body.appendChild(modal);

  // Set default expiry to 2 hours from now
  const expInput = modal.querySelector('[name="expiry_time"]');
  const now = new Date(Date.now() + 2 * 60 * 60 * 1000);
  expInput.value = now.toISOString().slice(0, 16);

  // Close
  document.getElementById("fb-donate-close").onclick = () => modal.remove();
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };

  // Use current location
  document.getElementById("fb-use-location").onclick = () => {
    if (!navigator.geolocation) return showToast("Geolocation not supported", "error");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        modal.querySelector('[name="pickup_lat"]').value = pos.coords.latitude.toFixed(6);
        modal.querySelector('[name="pickup_lng"]').value = pos.coords.longitude.toFixed(6);
        showToast("Location captured! ✅", "success");
      },
      () => showToast("Could not get location. Enter manually.", "warning")
    );
  };

  // Submit
  document.getElementById("fb-donate-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const err = document.getElementById("fb-donate-err");
    const ok  = document.getElementById("fb-donate-ok");
    err.style.display = "none";
    ok.style.display  = "none";

    const submitBtn = e.target.querySelector('[type="submit"]');
    submitBtn.textContent = "Submitting...";
    submitBtn.disabled = true;

    try {
      const result = await DonationsAPI.create(fd);
      ok.textContent = "✅ Donation submitted! ID: " + result.id + ". We are finding a match now.";
      ok.style.display = "block";
      submitBtn.textContent = "Submitted!";
      addActivityItem("heart", "donate", "You donated " + fd.get("quantity_serves") + " serves of " + fd.get("category") + " food", fd.get("pickup_address"), "New", "Just now");
      showToast("Donation submitted! 🎉", "success");
      setTimeout(() => modal.remove(), 2000);
    } catch(ex) {
      err.textContent = ex.message;
      err.style.display = "block";
      submitBtn.textContent = "Submit Donation";
      submitBtn.disabled = false;
    }
  };
}

// ── Request Food Modal ────────────────────────────────────────────────────────
function showRequestModal() {
  document.getElementById("fb-request-modal") && document.getElementById("fb-request-modal").remove();

  const modal = document.createElement("div");
  modal.id = "fb-request-modal";
  modal.style.cssText = "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.75);backdrop-filter:blur(8px);padding:1rem;";

  modal.innerHTML =
    '<div style="background:#0d0d14;border:1px solid rgba(255,255,255,0.12);border-radius:24px;padding:2.5rem;width:100%;max-width:440px;position:relative;">' +
      '<button id="fb-req-close" style="position:absolute;top:1rem;right:1.25rem;background:none;border:none;color:rgba(255,255,255,0.5);font-size:1.5rem;cursor:pointer;">✕</button>' +
      '<h2 style="font-family:Space Grotesk,sans-serif;font-size:1.4rem;color:white;margin-bottom:0.3rem;">🙏 Request Food</h2>' +
      '<p style="color:rgba(255,255,255,0.4);font-size:0.85rem;margin-bottom:1.5rem;">Tell us how many people need food and where.</p>' +

      '<form id="fb-request-form">' +
        '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Number of People</label>' +
        '<input name="people_count" type="number" min="1" placeholder="e.g. 10" required style="' + INPUT_STYLE + '">' +

        '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Urgency</label>' +
        '<select name="urgency" style="' + INPUT_STYLE + '">' +
          '<option value="low">🟢 Low</option>' +
          '<option value="medium" selected>🟡 Medium</option>' +
          '<option value="high">🟠 High</option>' +
          '<option value="critical">🔴 Critical</option>' +
        '</select>' +

        '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Delivery Address</label>' +
        '<input name="address" type="text" placeholder="Where should food be delivered?" required style="' + INPUT_STYLE + '">' +

        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;">' +
          '<div>' +
            '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Latitude</label>' +
            '<input name="lat" type="number" step="any" placeholder="e.g. 19.0760" required style="' + INPUT_STYLE + '">' +
          '</div>' +
          '<div>' +
            '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Longitude</label>' +
            '<input name="lng" type="number" step="any" placeholder="e.g. 72.8777" required style="' + INPUT_STYLE + '">' +
          '</div>' +
        '</div>' +

        '<button type="button" id="fb-req-location" style="width:100%;padding:0.6rem;background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.3);border-radius:10px;color:#8b5cf6;font-size:0.85rem;cursor:pointer;margin-bottom:0.75rem;">📍 Use My Current Location</button>' +

        '<label style="color:rgba(255,255,255,0.6);font-size:0.8rem;display:block;margin-bottom:0.3rem;">Additional Notes (optional)</label>' +
        '<input name="notes" type="text" placeholder="Any dietary restrictions?" style="' + INPUT_STYLE + '">' +

        '<button type="submit" style="width:100%;padding:0.9rem;background:linear-gradient(135deg,#8b5cf6,#7c3aed);color:white;border:none;border-radius:12px;font-weight:600;font-size:1rem;cursor:pointer;margin-top:0.25rem;">Submit Request</button>' +
        '<p id="fb-req-err" style="color:#ef4444;font-size:0.85rem;margin-top:0.5rem;display:none;"></p>' +
        '<p id="fb-req-ok"  style="color:#10b981;font-size:0.85rem;margin-top:0.5rem;display:none;"></p>' +
      '</form>' +
    '</div>';

  document.body.appendChild(modal);

  document.getElementById("fb-req-close").onclick = () => modal.remove();
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };

  document.getElementById("fb-req-location").onclick = () => {
    if (!navigator.geolocation) return showToast("Geolocation not supported", "error");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        modal.querySelector('[name="lat"]').value = pos.coords.latitude.toFixed(6);
        modal.querySelector('[name="lng"]').value = pos.coords.longitude.toFixed(6);
        showToast("Location captured! ✅", "success");
      },
      () => showToast("Could not get location. Enter manually.", "warning")
    );
  };

  document.getElementById("fb-request-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const err = document.getElementById("fb-req-err");
    const ok  = document.getElementById("fb-req-ok");
    err.style.display = "none";
    ok.style.display  = "none";

    const submitBtn = e.target.querySelector('[type="submit"]');
    submitBtn.textContent = "Submitting...";
    submitBtn.disabled = true;

    try {
      const result = await RequestsAPI.create({
        people_count: parseInt(fd.get("people_count")),
        urgency:      fd.get("urgency"),
        lat:          parseFloat(fd.get("lat")),
        lng:          parseFloat(fd.get("lng")),
        address:      fd.get("address"),
        notes:        fd.get("notes") || null,
      });
      ok.textContent = "✅ Request submitted! ID: " + result.id + ". We are finding food for you.";
      ok.style.display = "block";
      submitBtn.textContent = "Submitted!";
      showToast("Food request submitted! 🙏", "success");
      setTimeout(() => modal.remove(), 2000);
    } catch(ex) {
      err.textContent = ex.message;
      err.style.display = "block";
      submitBtn.textContent = "Submit Request";
      submitBtn.disabled = false;
    }
  };
}
