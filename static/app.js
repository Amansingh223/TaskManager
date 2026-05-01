const state = {
  token: localStorage.getItem("token"),
  user: JSON.parse(localStorage.getItem("user") || "null"),
  users: [],
  projects: [],
  selectedProjectId: null,
  mode: "login",
};

const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

function setMessage(text, target = "#appMessage") {
  $(target).textContent = text || "";
}

function setAuthMode(mode) {
  state.mode = mode;
  $("#loginTab").classList.toggle("active", mode === "login");
  $("#signupTab").classList.toggle("active", mode === "signup");
  $("#authSubmit").textContent = mode === "login" ? "Login" : "Create account";
  $("#nameInput").parentElement.classList.toggle("hidden", mode === "login");
  $("#roleField").classList.toggle("hidden", mode === "login");
  $("#passwordInput").autocomplete = mode === "login" ? "current-password" : "new-password";
  setMessage("", "#authMessage");
}

function showApp(isAuthed) {
  $("#authView").classList.toggle("hidden", isAuthed);
  $("#appView").classList.toggle("hidden", !isAuthed);
  if (!isAuthed) return;
  $("#userName").textContent = state.user.name;
  $("#userRole").textContent = `${state.user.role} account`;
  document.querySelectorAll(".admin-only").forEach((el) => {
    el.classList.toggle("hidden", state.user.role !== "Admin");
  });
}

function saveSession(data) {
  state.token = data.token;
  state.user = data.user;
  localStorage.setItem("token", data.token);
  localStorage.setItem("user", JSON.stringify(data.user));
}

function clearSession() {
  state.token = null;
  state.user = null;
  localStorage.removeItem("token");
  localStorage.removeItem("user");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

function formatDue(date) {
  return date ? `Due ${date}` : "No due date";
}

function initials(name) {
  return String(name || "User")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

function isOverdue(task) {
  const today = new Date().toISOString().slice(0, 10);
  return task.due_date && task.due_date < today && task.status !== "Done";
}

function renderTask(task, options = {}) {
  const { canManage = false, members = [], projectId = null } = options;
  const node = $("#taskTemplate").content.firstElementChild.cloneNode(true);
  node.dataset.status = task.status.toLowerCase().replace(/\s+/g, "-");
  node.querySelector("h3").textContent = task.title;

  const bits = [task.project_name, task.assignee_name && `Assigned to ${task.assignee_name}`, formatDue(task.due_date)].filter(Boolean);
  node.querySelector("p").innerHTML = `${escapeHtml(bits.join(" / "))}${isOverdue(task) ? ' <span class="overdue-label">Overdue</span>' : ""}`;

  const select = node.querySelector(".task-status");
  const editButton = node.querySelector(".edit-task");
  const deleteButton = node.querySelector(".delete-task");
  select.value = task.status;
  editButton.classList.toggle("hidden", !canManage);
  deleteButton.classList.toggle("hidden", !canManage);

  select.addEventListener("change", async () => {
    try {
      await api(`/api/tasks/${task.id}`, { method: "PATCH", body: JSON.stringify({ status: select.value }) });
      await refreshAll();
      if (projectId) await selectProject(projectId);
    } catch (error) {
      setMessage(error.message);
      select.value = task.status;
    }
  });

  editButton.addEventListener("click", () => {
    const existingForm = node.querySelector(".task-edit-form");
    if (existingForm) {
      existingForm.remove();
      return;
    }
    node.appendChild(renderTaskEditForm(task, members, projectId));
  });

  deleteButton.addEventListener("click", async () => {
    if (!confirm(`Delete task "${task.title}"?`)) return;
    try {
      await api(`/api/tasks/${task.id}`, { method: "DELETE" });
      await refreshAll();
      if (projectId) await selectProject(projectId);
    } catch (error) {
      setMessage(error.message);
    }
  });

  return node;
}

function renderTaskEditForm(task, members, projectId) {
  const form = document.createElement("form");
  form.className = "task-edit-form";
  const memberOptions = members
    .map((member) => `<option value="${member.id}" ${member.id === task.assignee_id ? "selected" : ""}>${escapeHtml(member.name)}</option>`)
    .join("");

  form.innerHTML = `
    <input name="title" value="${escapeHtml(task.title)}" placeholder="Task title" required minlength="2">
    <select name="assigneeId">
      <option value="">Unassigned</option>
      ${memberOptions}
    </select>
    <select name="status">
      <option ${task.status === "Todo" ? "selected" : ""}>Todo</option>
      <option ${task.status === "In Progress" ? "selected" : ""}>In Progress</option>
      <option ${task.status === "Done" ? "selected" : ""}>Done</option>
    </select>
    <input name="dueDate" type="date" value="${escapeHtml(task.due_date || "")}">
    <textarea name="description" placeholder="Task description">${escapeHtml(task.description || "")}</textarea>
    <div class="form-actions">
      <button class="primary" type="submit">Save</button>
      <button class="ghost cancel-edit" type="button">Cancel</button>
    </div>
  `;

  form.querySelector(".cancel-edit").addEventListener("click", () => form.remove());
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    try {
      await api(`/api/tasks/${task.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: data.get("title"),
          assigneeId: data.get("assigneeId") || null,
          status: data.get("status"),
          dueDate: data.get("dueDate") || null,
          description: data.get("description"),
        }),
      });
      await refreshAll();
      if (projectId) await selectProject(projectId);
    } catch (error) {
      setMessage(error.message);
    }
  });

  return form;
}

async function loadDashboard() {
  const data = await api("/api/dashboard");
  $("#todoCount").textContent = data.statusCounts.Todo || 0;
  $("#progressCount").textContent = data.statusCounts["In Progress"] || 0;
  $("#doneCount").textContent = data.statusCounts.Done || 0;
  $("#overdueCount").textContent = data.overdue || 0;
  const list = $("#assignedList");
  list.innerHTML = "";
  if (!data.assignedTasks.length) {
    list.innerHTML = '<div class="empty-state detail-pane"><strong>No assigned tasks yet.</strong><span>Your focused work will appear here.</span></div>';
    return;
  }
  data.assignedTasks.forEach((task) => list.appendChild(renderTask(task)));
}

async function loadUsers() {
  const data = await api("/api/users");
  state.users = data.users;
  const list = $("#teamList");
  list.innerHTML = "";
  data.users.forEach((user) => {
    const card = document.createElement("article");
    card.className = "team-card";
    card.innerHTML = `
      <div class="avatar">${escapeHtml(initials(user.name))}</div>
      <div>
        <h3>${escapeHtml(user.name)}</h3>
        <p>${escapeHtml(user.email)}</p>
      </div>
      <span class="role-badge">${escapeHtml(user.role)}</span>
    `;
    list.appendChild(card);
  });
}

async function loadProjects() {
  const data = await api("/api/projects");
  state.projects = data.projects;
  const list = $("#projectList");
  list.innerHTML = "";
  if (!data.projects.length) {
    list.innerHTML = '<div class="empty-state detail-pane"><strong>No projects yet.</strong><span>New projects will show progress, members, and tasks here.</span></div>';
    $("#projectDetail").className = "detail-pane empty-state";
    $("#projectDetail").textContent = state.user.role === "Admin" ? "Create a project to begin." : "Ask an admin to add you to a project.";
    return;
  }
  data.projects.forEach((project) => {
    const done = Number(project.done_count || 0);
    const total = Number(project.task_count || 0);
    const pct = total ? Math.round((done / total) * 100) : 0;
    const card = document.createElement("article");
    card.className = "project-card";
    card.innerHTML = `
      <div class="project-card-head">
        <h3>${escapeHtml(project.name)}</h3>
        <span>${pct}%</span>
      </div>
      <p>${escapeHtml(project.description || "No description")}</p>
      <div class="card-meta">
        <span>${project.member_count} members</span>
        <span>${total} tasks</span>
        <span>${formatDue(project.due_date)}</span>
      </div>
      <div class="progress"><span style="width:${pct}%"></span></div>
      <button class="ghost" type="button">Open</button>
    `;
    card.querySelector("button").addEventListener("click", () => selectProject(project.id));
    list.appendChild(card);
  });
  if (state.selectedProjectId) await selectProject(state.selectedProjectId, false);
}

async function selectProject(projectId, showErrors = true) {
  try {
    state.selectedProjectId = projectId;
    const data = await api(`/api/projects/${projectId}`);
    renderProjectDetail(data);
  } catch (error) {
    if (showErrors) setMessage(error.message);
  }
}

function renderProjectDetail(data) {
  const pane = $("#projectDetail");
  pane.className = "detail-pane";
  const memberOptions = data.members.map((member) => `<option value="${member.id}">${escapeHtml(member.name)}</option>`).join("");
  const allUserOptions = state.users
    .filter((user) => !data.members.some((member) => member.id === user.id))
    .map((user) => `<option value="${user.id}">${escapeHtml(user.name)} (${escapeHtml(user.role)})</option>`)
    .join("");
  const canManage = state.user.role === "Admin" || data.project.owner_id === state.user.id;

  pane.innerHTML = `
    <div class="section-heading">
      <div>
        <p class="eyebrow">Project detail</p>
        <h2>${escapeHtml(data.project.name)}</h2>
        <p class="muted">${escapeHtml(data.project.description || "No description")}</p>
      </div>
    </div>
    <div class="member-strip">${data.members.map((member) => `<span class="pill">${escapeHtml(member.name)}</span>`).join("")}</div>
    <form id="memberForm" class="toolbar ${canManage ? "" : "hidden"}">
      <select id="memberSelect">${allUserOptions || "<option value=''>No users available</option>"}</select>
      <button class="ghost" type="submit">Add member</button>
    </form>
    <form id="taskForm" class="detail-actions ${canManage ? "" : "hidden"}">
      <input id="taskTitle" placeholder="Task title" required minlength="2">
      <select id="taskAssignee"><option value="">Unassigned</option>${memberOptions}</select>
      <select id="taskStatus"><option>Todo</option><option>In Progress</option><option>Done</option></select>
      <input id="taskDue" type="date">
      <textarea id="taskDescription" placeholder="Task description"></textarea>
      <button class="primary" type="submit">Create task</button>
    </form>
    <div id="projectTasks" class="task-list"></div>
  `;

  if (canManage) {
    $("#memberForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const userId = $("#memberSelect").value;
      if (!userId) return;
      await api(`/api/projects/${data.project.id}/members`, { method: "POST", body: JSON.stringify({ userId }) });
      await refreshAll();
      await selectProject(data.project.id);
    });

    $("#taskForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      await api("/api/tasks", {
        method: "POST",
        body: JSON.stringify({
          projectId: data.project.id,
          title: $("#taskTitle").value,
          description: $("#taskDescription").value,
          assigneeId: $("#taskAssignee").value || null,
          status: $("#taskStatus").value,
          dueDate: $("#taskDue").value || null,
        }),
      });
      event.target.reset();
      await refreshAll();
      await selectProject(data.project.id);
    });
  }

  const taskList = $("#projectTasks");
  if (!data.tasks.length) {
    taskList.innerHTML = '<div class="empty-state detail-pane"><strong>No tasks in this project.</strong><span>Create the first task to start tracking delivery.</span></div>';
    return;
  }
  data.tasks.forEach((task) => {
    taskList.appendChild(renderTask(
      { ...task, project_name: data.project.name },
      { canManage, members: data.members, projectId: data.project.id },
    ));
  });
}

function switchView(view) {
  document.querySelectorAll(".view").forEach((el) => el.classList.add("hidden"));
  $(`#${view}View`).classList.remove("hidden");
  document.querySelectorAll(".nav-button").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $("#pageTitle").textContent = view[0].toUpperCase() + view.slice(1);
}

async function refreshAll() {
  if (!state.token) return;
  try {
    setMessage("");
    showApp(true);
    await Promise.all([loadUsers(), loadDashboard()]);
    await loadProjects();
  } catch (error) {
    if (error.message === "Authentication required") {
      clearSession();
      showApp(false);
    } else {
      setMessage(error.message);
    }
  }
}

$("#loginTab").addEventListener("click", () => setAuthMode("login"));
$("#signupTab").addEventListener("click", () => setAuthMode("signup"));

$("#authForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = {
      email: $("#emailInput").value,
      password: $("#passwordInput").value,
    };
    if (state.mode === "signup") {
      payload.name = $("#nameInput").value;
      payload.role = $("#roleInput").value;
    }
    const data = await api(state.mode === "login" ? "/api/login" : "/api/signup", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    saveSession(data);
    showApp(true);
    await refreshAll();
  } catch (error) {
    setMessage(error.message, "#authMessage");
  }
});

$("#logoutButton").addEventListener("click", () => {
  clearSession();
  showApp(false);
});

$("#refreshButton").addEventListener("click", refreshAll);

document.querySelectorAll(".nav-button").forEach((button) => {
  button.addEventListener("click", () => switchView(button.dataset.view));
});

$("#projectForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/projects", {
      method: "POST",
      body: JSON.stringify({
        name: $("#projectName").value,
        description: $("#projectDescription").value,
        dueDate: $("#projectDue").value || null,
      }),
    });
    event.target.reset();
    await refreshAll();
  } catch (error) {
    setMessage(error.message);
  }
});

setAuthMode("login");
showApp(Boolean(state.token && state.user));
refreshAll();
