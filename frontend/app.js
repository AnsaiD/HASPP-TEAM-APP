/* HASPP Team App — frontend */
const T = {
  so: {
    login: "Gal", register: "Isdiiwaangeli", name: "Magaca", email: "Email",
    password: "Password", haveAccount: "Ma leedahay akoon? Gal",
    noAccount: "Akoon ma lihid? Isdiiwaangeli",
    firstUser: "Qofka ugu horreeya ee isdiiwaangeliya wuxuu noqonayaa Admin.",
    boards: "Boards", newBoard: "+ Board cusub", boardTitle: "Magaca board-ka",
    boardDesc: "Faahfaahin (optional)", create: "Abuur", cancel: "Jooji",
    open: "Fur", back: "← Dib u noqo", admin: "Maamul", members: "Xubnaha",
    addList: "+ List", newCard: "+ Kaar", save: "Kaydi", delete: "Tirtir",
    edit: "Beddel", cardTitle: "Cinwaanka", description: "Faahfaahin",
    assignee: "U qoondee", none: "— Qofna —", dueDate: "Taariikhda",
    users: "Isticmaalayaasha", role: "Door", active: "Firfircoon",
    boardMembers: "Xubnaha board-ka", addMember: "Ku dar xubin",
    selectUser: "Dooro qof", add: "Dar", remove: "Ka saar",
    logout: "Bax", today: "Maanta", overdue: "Wakhtigu dhacay",
    wrongCreds: "Email ama password khaldan", emailTaken: "Email-kan waa la isticmaalay",
    confirmDelete: "Ma hubtaa inaad tirtirto?", dashboard: "Bogga hore",
    noBoards: "Wali board ma jiro. Samee mid cusub!",
    cannotDeactivateSelf: "Ma joojin kartid naftaada",
    member: "member", adminRole: "admin",
    deleteBoard: "Tirtir board-ka",
    addUser: "Ku dar user cusub",
    confirmDeleteUser: "Ma hubtaa inaad TIRTIRTO user-kan? Tani waa permanent!",
    cannotDeleteSelf: "Ma tirtiri kartid naftaada",
    cannotDeleteLastAdmin: "Ma tirtiri kartid admin-ka ugu dambeeya",
    wakingUp: "Server-ku waa toosayaa, fadlan sug…",
    retry: "Isku day mar kale",
    networkError: "Server-ka lama xiriirin. Sug daqiiqo kadibna isku day mar kale.",
  },
  en: {
    login: "Log in", register: "Sign up", name: "Name", email: "Email",
    password: "Password", haveAccount: "Have an account? Log in",
    noAccount: "No account? Sign up",
    firstUser: "The first person to sign up becomes Admin.",
    boards: "Boards", newBoard: "+ New board", boardTitle: "Board title",
    boardDesc: "Description (optional)", create: "Create", cancel: "Cancel",
    open: "Open", back: "← Back", admin: "Admin", members: "Members",
    addList: "+ List", newCard: "+ Card", save: "Save", delete: "Delete",
    edit: "Edit", cardTitle: "Title", description: "Description",
    assignee: "Assign to", none: "— Nobody —", dueDate: "Due date",
    users: "Users", role: "Role", active: "Active",
    boardMembers: "Board members", addMember: "Add member",
    selectUser: "Select person", add: "Add", remove: "Remove",
    logout: "Log out", today: "Today", overdue: "Overdue",
    wrongCreds: "Wrong email or password", emailTaken: "Email already used",
    confirmDelete: "Are you sure you want to delete?", dashboard: "Dashboard",
    noBoards: "No boards yet. Create one!",
    cannotDeactivateSelf: "You cannot deactivate yourself",
    member: "member", adminRole: "admin",
    deleteBoard: "Delete board",
    addUser: "Add new user",
    confirmDeleteUser: "Are you sure you want to DELETE this user? This is permanent!",
    cannotDeleteSelf: "You cannot delete yourself",
    cannotDeleteLastAdmin: "Cannot delete the last admin",
    wakingUp: "Server is waking up, please wait…",
    retry: "Retry",
    networkError: "Could not reach the server. Wait a moment and try again.",
  }
};
let lang = localStorage.getItem("hta_lang") || "so";
const t = (k) => T[lang][k] || k;
const $ = (s) => document.querySelector(s);
const app = $("#app");
let token = localStorage.getItem("hta_token");
let me = null;
let view = "dashboard";
let currentBoard = null;

async function api(path, method = "GET", body = null) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = "Bearer " + token;
  const res = await fetch("/api" + path, {
    method, headers, body: body ? JSON.stringify(body) : null,
  });
  if (res.status === 401) { doLogout(); throw new Error("auth"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || ("Error " + res.status));
  return data;
}

function doLogout() {
  token = null; me = null; currentBoard = null; view = "dashboard";
  localStorage.removeItem("hta_token");
  render();
}

/* ---------- auth views ---------- */
function renderAuth(mode = "login") {
  const isLogin = mode === "login";
  app.innerHTML = `
    <div class="auth-box">
      <h2>☀️ HASPP Team — ${isLogin ? t("login") : t("register")}</h2>
      <div class="error hidden" id="err"></div>
      ${isLogin ? "" : `<input id="fName" placeholder="${t("name")}">`}
      <input id="fEmail" type="email" placeholder="${t("email")}">
      <input id="fPass" type="password" placeholder="${t("password")}">
      <button class="btn" id="goBtn" style="width:100%">${isLogin ? t("login") : t("register")}</button>
      <p class="hint"><span class="link" id="switchMode">${isLogin ? t("noAccount") : t("haveAccount")}</span></p>
      ${isLogin ? "" : `<p class="hint">${t("firstUser")}</p>`}
    </div>`;
  $("#switchMode").onclick = () => renderAuth(isLogin ? "register" : "login");
  $("#goBtn").onclick = async () => {
    $("#err").classList.add("hidden");
    try {
      const email = $("#fEmail").value.trim(), password = $("#fPass").value;
      const data = isLogin
        ? await api("/login", "POST", { email, password })
        : await api("/register", "POST", { name: $("#fName").value.trim(), email, password });
      token = data.token; me = data.user;
      localStorage.setItem("hta_token", token);
      view = "dashboard"; render();
    } catch (e) {
      const el = $("#err");
      const msg = e.message || "";
      el.textContent = msg.includes("registered") ? t("emailTaken")
        : msg === "auth" ? t("wrongCreds")
        : t("networkError");
      el.classList.remove("hidden");
    }
  };
}

/* ---------- dashboard ---------- */
async function renderDashboard() {
  const boards = await api("/boards");
  app.innerHTML = `
    <div class="toolbar">
      <h2>${t("boards")}</h2>
      <input id="nbTitle" placeholder="${t("boardTitle")}">
      <button class="btn" id="nbBtn">${t("newBoard")}</button>
      ${me.role === "admin" ? `<button class="btn btn-gold" id="adminBtn">⚙️ ${t("admin")}</button>` : ""}
    </div>
    <div class="board-grid">
      ${boards.length ? boards.map(b => `
        <div class="board-card" data-id="${b.id}">
          <h3>${esc(b.title)}</h3><p>${esc(b.description || "")}</p>
        </div>`).join("") : `<p class="hint">${t("noBoards")}</p>`}
    </div>`;
  $("#nbBtn").onclick = async () => {
    const title = $("#nbTitle").value.trim();
    if (!title) return;
    await api("/boards", "POST", { title, description: "" });
    $("#nbTitle").value = "";
    renderDashboard();
  };
  document.querySelectorAll(".board-card").forEach(c =>
    c.onclick = () => { currentBoard = +c.dataset.id; view = "board"; render(); });
  const ab = $("#adminBtn");
  if (ab) ab.onclick = () => { view = "admin"; render(); };
}

/* ---------- board / kanban ---------- */
async function renderBoard() {
  const b = await api("/boards/" + currentBoard);
  currentBoardData = b;
  const isBAdmin = me.role === "admin" || b.members.some(m => m.id === me.id && m.role === "admin");
  app.innerHTML = `
    <div class="toolbar">
      <button class="btn-outline btn" id="backBtn">${t("back")}</button>
      <h2>${esc(b.title)}</h2>
      <input id="nlTitle" placeholder="${t("addList")}" style="margin-left:auto">
      <button class="btn" id="nlBtn">${t("addList")}</button>
      <button class="btn btn-outline" id="memBtn">👥 ${t("members")} (${b.members.length})</button>
      ${isBAdmin ? `<button class="btn btn-danger" id="delBoardBtn">${t("deleteBoard")}</button>` : ""}
    </div>
    <div class="kanban" id="kanban">
      ${b.lists.map(l => `
        <div class="list" data-lid="${l.id}">
          <h3>${esc(l.title)} ${isBAdmin ? `<span class="del" data-del-list="${l.id}">✕</span>` : ""}</h3>
          <div class="cards" data-lid="${l.id}">
            ${l.cards.map(c => cardHtml(c)).join("")}
          </div>
          <button class="btn btn-outline add-card" data-add="${l.id}">${t("newCard")}</button>
        </div>`).join("")}
    </div>`;
  $("#backBtn").onclick = () => { view = "dashboard"; render(); };
  $("#nlBtn").onclick = async () => {
    const title = $("#nlTitle").value.trim(); if (!title) return;
    await api(`/boards/${currentBoard}/lists`, "POST", { title });
    $("#nlTitle").value = "";
    renderBoard();
  };
  $("#memBtn").onclick = () => showMembersModal(b, isBAdmin);
  const delB = $("#delBoardBtn");
  if (delB) delB.onclick = async () => {
    if (!confirm(t("confirmDelete"))) return;
    await api("/boards/" + currentBoard, "DELETE");
    view = "dashboard"; currentBoard = null; render();
  };
  document.querySelectorAll("[data-del-list]").forEach(el =>
    el.onclick = async (e) => {
      e.stopPropagation();
      if (!confirm(t("confirmDelete"))) return;
      await api("/lists/" + el.dataset.delList, "DELETE");
      renderBoard();
    });
  document.querySelectorAll("[data-add]").forEach(el =>
    el.onclick = () => showCardModal(+el.dataset.add));
  document.querySelectorAll("[data-edit]").forEach(el =>
    el.onclick = (e) => { e.stopPropagation(); showCardModal(null, +el.dataset.edit); });
  document.querySelectorAll("[data-del-card]").forEach(el =>
    el.onclick = async (e) => {
      e.stopPropagation();
      if (!confirm(t("confirmDelete"))) return;
      await api("/cards/" + el.dataset.delCard, "DELETE");
      renderBoard();
    });
  enableDragDrop(b);
}
let currentBoardData = null;

function cardHtml(c) {
  let due = "";
  if (c.due_date) {
    const d = new Date(c.due_date + "T23:59:59");
    const late = d < new Date() && !isDoneList(c);
    due = `<div class="meta ${late ? "due" : ""}">📅 ${c.due_date}${late ? " — " + t("overdue") : ""}</div>`;
  }
  return `<div class="card" draggable="true" data-cid="${c.id}">
    <div><strong>${esc(c.title)}</strong></div>
    ${c.assignee_name ? `<div class="meta">👤 ${esc(c.assignee_name)}</div>` : ""}${due}
    <div class="actions">
      <button data-edit="${c.id}">${t("edit")}</button>
      <button data-del-card="${c.id}">${t("delete")}</button>
    </div></div>`;
}
function isDoneList() { return false; }

function enableDragDrop(b) {
  let dragCid = null;
  document.querySelectorAll(".card").forEach(card => {
    card.addEventListener("dragstart", () => { dragCid = +card.dataset.cid; card.classList.add("dragging"); });
    card.addEventListener("dragend", () => card.classList.remove("dragging"));
  });
  document.querySelectorAll(".list").forEach(list => {
    list.addEventListener("dragover", (e) => { e.preventDefault(); list.classList.add("drag-over"); });
    list.addEventListener("dragleave", () => list.classList.remove("drag-over"));
    list.addEventListener("drop", async (e) => {
      e.preventDefault(); list.classList.remove("drag-over");
      const lid = +list.dataset.lid;
      const cardsEl = list.querySelector(".cards");
      const pos = cardsEl.querySelectorAll(".card").length;
      await api("/cards/" + dragCid, "PATCH", { list_id: lid, position: pos });
      renderBoard();
    });
  });
}

function showCardModal(listId, cardId = null) {
  const b = currentBoardData;
  let card = null;
  if (cardId) for (const l of b.lists) { const f = l.cards.find(c => c.id === cardId); if (f) card = f; }
  const opts = b.members.map(m =>
    `<option value="${m.id}" ${card && card.assignee_id === m.id ? "selected" : ""}>${esc(m.name)}</option>`).join("");
  const bd = document.createElement("div");
  bd.className = "modal-backdrop";
  bd.innerHTML = `<div class="modal">
    <h3>${card ? t("edit") : t("newCard")}</h3>
    <input id="mTitle" placeholder="${t("cardTitle")}" value="${card ? esc(card.title) : ""}">
    <textarea id="mDesc" placeholder="${t("description")}">${card ? esc(card.description || "") : ""}</textarea>
    <label class="hint">${t("assignee")}</label>
    <select id="mAssign"><option value="">${t("none")}</option>${opts}</select>
    <label class="hint">${t("dueDate")}</label>
    <input id="mDue" type="date" value="${card && card.due_date ? card.due_date : ""}">
    <div class="row">
      <button class="btn btn-outline" id="mCancel">${t("cancel")}</button>
      <button class="btn" id="mSave">${t("save")}</button>
    </div></div>`;
  document.body.appendChild(bd);
  $("#mCancel").onclick = () => bd.remove();
  bd.onclick = (e) => { if (e.target === bd) bd.remove(); };
  $("#mSave").onclick = async () => {
    const payload = {
      title: $("#mTitle").value.trim(),
      description: $("#mDesc").value.trim(),
      assignee_id: $("#mAssign").value ? +$("#mAssign").value : null,
      due_date: $("#mDue").value || null,
    };
    if (!payload.title) return;
    if (card) await api("/cards/" + card.id, "PATCH", payload);
    else await api("/lists/" + listId + "/cards", "POST", payload);
    bd.remove(); renderBoard();
  };
}

async function showMembersModal(b, isBAdmin) {
  const allUsers = me.role === "admin" ? await api("/users") : [];
  const bd = document.createElement("div");
  bd.className = "modal-backdrop";
  const rows = b.members.map(m => `
    <div class="toolbar" style="justify-content:space-between">
      <span>${esc(m.name)} <span class="badge ${m.role}">${m.role}</span></span>
      ${isBAdmin && m.id !== me.id ? `<button class="btn-small btn-danger" data-rm="${m.id}">${t("remove")}</button>` : ""}
    </div>`).join("");
  bd.innerHTML = `<div class="modal">
    <h3>👥 ${t("boardMembers")}</h3>${rows}
    ${isBAdmin && allUsers.length ? `
      <hr style="margin:12px 0"><label class="hint">${t("addMember")}</label>
      <select id="muSel">${allUsers.filter(u => !b.members.some(m => m.id === u.id) && u.is_active)
        .map(u => `<option value="${u.id}">${esc(u.name)} (${esc(u.email)})</option>`).join("")}</select>
      <div class="row"><button class="btn" id="muAdd">${t("add")}</button></div>` : ""}
    <div class="row"><button class="btn btn-outline" id="mClose">${t("cancel")}</button></div>
  </div>`;
  document.body.appendChild(bd);
  $("#mClose").onclick = () => bd.remove();
  bd.onclick = (e) => { if (e.target === bd) bd.remove(); };
  bd.querySelectorAll("[data-rm]").forEach(el => el.onclick = async () => {
    await api(`/boards/${b.id}/members/${el.dataset.rm}`, "DELETE");
    bd.remove(); renderBoard();
  });
  const addBtn = $("#muAdd");
  if (addBtn) addBtn.onclick = async () => {
    const uid = $("#muSel").value; if (!uid) return;
    await api(`/boards/${b.id}/members`, "POST", { user_id: +uid, role: "member" });
    bd.remove(); renderBoard();
  };
}

/* ---------- admin panel ---------- */
async function renderAdmin() {
  const users = await api("/users");
  app.innerHTML = `
    <div class="toolbar">
      <button class="btn-outline btn" id="backBtn">${t("back")}</button>
      <h2>⚙️ ${t("admin")} — ${t("users")}</h2>
    </div>
    <p class="hint">${t("firstUser")}</p>
    <div class="add-user-form">
      <h3>➕ ${t("addUser")}</h3>
      <input id="nuName" placeholder="${t("name")}">
      <input id="nuEmail" placeholder="${t("email")}" type="email">
      <input id="nuPass" placeholder="${t("password")}" type="password">
      <select id="nuRole">
        <option value="member">${t("member")}</option>
        <option value="admin">${t("adminRole")}</option>
      </select>
      <button class="btn" id="nuAdd">${t("add")}</button>
    </div>
    <table class="admin-table">
      <tr><th>${t("name")}</th><th>${t("email")}</th><th>${t("role")}</th><th>${t("active")}</th><th></th></tr>
      ${users.map(u => `
        <tr>
          <td>${esc(u.name)} ${u.id === me.id ? "(you)" : ""}</td>
          <td>${esc(u.email)}</td>
          <td><span class="badge ${u.role}">${u.role}</span></td>
          <td>${u.is_active ? "✅" : `<span class="badge off">off</span>`}</td>
          <td>
            <select data-role="${u.id}" ${u.id === me.id ? "disabled" : ""}>
              <option value="member" ${u.role === "member" ? "selected" : ""}>member</option>
              <option value="admin" ${u.role === "admin" ? "selected" : ""}>admin</option>
            </select>
            ${u.id !== me.id ? `<button class="btn-small ${u.is_active ? "btn-danger" : ""}" data-toggle="${u.id}">
              ${u.is_active ? "Deactivate" : "Activate"}</button>
            <button class="btn-small btn-danger" data-deluser="${u.id}">🗑️ ${t("delete")}</button>` : ""}
          </td>
        </tr>`).join("")}
    </table>`;
  $("#backBtn").onclick = () => { view = "dashboard"; render(); };
  document.querySelectorAll("[data-role]").forEach(sel =>
    sel.onchange = async () => {
      await api("/users/" + sel.dataset.role, "PATCH", { role: sel.value });
      renderAdmin();
    });
  document.querySelectorAll("[data-toggle]").forEach(btn =>
    btn.onclick = async () => {
      const id = +btn.dataset.toggle;
      const u = users.find(x => x.id === id);
      if (u.is_active && !confirm(t("confirmDelete"))) return;
      await api("/users/" + id, "PATCH", { is_active: !u.is_active });
      renderAdmin();
    });
  document.querySelectorAll("[data-deluser]").forEach(btn =>
    btn.onclick = async () => {
      if (!confirm(t("confirmDeleteUser"))) return;
      try {
        await api("/users/" + btn.dataset.deluser, "DELETE");
        renderAdmin();
      } catch (e) { alert(e.message); }
    });
  $("#nuAdd").onclick = async () => {
    const body = {
      name: $("#nuName").value.trim(),
      email: $("#nuEmail").value.trim(),
      password: $("#nuPass").value,
      role: $("#nuRole").value,
    };
    if (!body.name || !body.email || body.password.length < 6) {
      alert(t("wrongCreds"));
      return;
    }
    try {
      await api("/users", "POST", body);
      $("#nuName").value = "";
      $("#nuEmail").value = "";
      $("#nuPass").value = "";
      $("#nuRole").value = "member";
      renderAdmin();
    } catch (e) { alert(e.message); }
  };
}

/* ---------- main render ---------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function render(attempt = 0) {
  document.documentElement.lang = lang;
  $("#langToggle").textContent = lang === "so" ? "EN" : "SO";
  $("#logoutBtn").textContent = t("logout");
  if (!token) {
    $("#userInfo").classList.add("hidden"); $("#logoutBtn").classList.add("hidden");
    renderAuth(); return;
  }
  try {
    if (!me) me = await api("/me");
  } catch {
    if (!token || attempt >= 10) { renderAuth(); return; }  // invalid token → real login page
    // Network error = server waking up. Don't show login page — retry instead.
    app.innerHTML = `<div class="center"><p class="hint">⏳ ${t("wakingUp")}</p>
      <button class="btn" id="retryBtn">${t("retry")}</button></div>`;
    $("#retryBtn").onclick = () => render();
    setTimeout(() => { if (token && !me) render(attempt + 1); }, 6000);
    return;
  }
  $("#userInfo").textContent = `${me.name} (${me.role})`;
  $("#userInfo").classList.remove("hidden");
  $("#logoutBtn").classList.remove("hidden");
  try {
    if (view === "dashboard") await renderDashboard();
    else if (view === "board") await renderBoard();
    else if (view === "admin") {
      if (me.role !== "admin") { view = "dashboard"; await renderDashboard(); }
      else await renderAdmin();
    }
  } catch (e) { if (e.message !== "auth") app.innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

$("#langToggle").onclick = () => {
  lang = lang === "so" ? "en" : "so";
  localStorage.setItem("hta_lang", lang);
  render();
};
$("#logoutBtn").onclick = doLogout;
render();
