const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const initData = tg?.initData || "";
const user = tg?.initDataUnsafe?.user || null;
const notice = document.querySelector("#notice");

function showNotice(message) {
  notice.textContent = message;
  notice.classList.add("visible");
  window.clearTimeout(showNotice.timer);
  showNotice.timer = window.setTimeout(() => notice.classList.remove("visible"), 3500);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "So'rov bajarilmadi");
  }
  return data;
}

function identityPayload() {
  return {
    init_data: initData,
    user: user
      ? {
          id: user.id,
          first_name: user.first_name || "",
          last_name: user.last_name || "",
          username: user.username || "",
        }
      : null,
  };
}

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
    document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
    button.classList.add("active");
    document.querySelector(`#${button.dataset.tab}View`).classList.add("active");
    if (button.dataset.tab === "status") {
      loadStatus();
    }
    if (button.dataset.tab === "portfolio") {
      loadPortfolio();
    }
  });
});

document.querySelector("#closeButton").addEventListener("click", () => tg?.close());

const requirements = document.querySelector("#requirements");
requirements.addEventListener("input", () => {
  document.querySelector("#characterCount").textContent = `${requirements.value.length} / 4000`;
});

document.querySelector("#calculatorTemplate").addEventListener("click", () => {
  const template = [
    "1. Loyiha maqsadi nima?",
    "2. Foydalanuvchi nimalar qiladi?",
    "3. Admin nimalar qiladi?",
    "4. Qanday ma'lumotlar saqlanadi?",
    "5. Bildirishnoma, SMS, API, fayl yuklash yoki boshqa integratsiya kerakmi?",
    "6. Loyiha ichidagi naqd to'lov jarayoni qanday ishlaydi?",
  ].join("\n");
  requirements.value = requirements.value.trim()
    ? `${requirements.value.trim()}\n\n${template}`
    : template;
  requirements.dispatchEvent(new Event("input"));
  requirements.focus();
});

document.querySelector("#orderForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/webapp/order", {
      method: "POST",
      body: JSON.stringify({
        ...identityPayload(),
        project: document.querySelector("#project").value,
        requirements: requirements.value.trim(),
      }),
    });
    showNotice(`Buyurtma #${result.order_id} qabul qilindi. Telegram chatdagi to'lov savolini tekshiring.`);
    event.target.reset();
    document.querySelector("#characterCount").textContent = "0 / 4000";
  } catch (error) {
    showNotice(error.message);
  }
});

async function loadStatus() {
  const content = document.querySelector("#statusContent");
  content.textContent = "Yuklanmoqda...";
  try {
    const result = await api("/api/webapp/status", {
      method: "POST",
      body: JSON.stringify(identityPayload()),
    });
    if (!result.order) {
      content.textContent = "Sizda hali buyurtma yo'q.";
      return;
    }
    const order = result.order;
    content.innerHTML = `
      <strong>Buyurtma #${order.id}</strong><br>
      ${order.project}<br>
      Holat: ${order.status}<br>
      CRM bosqich: ${order.pipeline}<br>
      Narx: $${order.estimate}<br>
      Predoplata: $${order.prepayment}<br>
      Muddat: ${order.duration || "-"}
    `;
  } catch (error) {
    content.textContent = error.message;
  }
}

document.querySelector("#refreshStatus").addEventListener("click", loadStatus);

async function loadPortfolio() {
  const list = document.querySelector("#portfolioList");
  if (list.childElementCount) return;
  try {
    const result = await api("/api/webapp/portfolio");
    result.items.forEach((item) => {
      const article = document.createElement("article");
      article.className = "list-item";
      article.innerHTML = `<h2>${item.title}</h2><p>${item.description}</p>`;
      list.appendChild(article);
    });
  } catch (error) {
    showNotice(error.message);
  }
}

document.querySelector("#supportForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#supportMessage");
  try {
    const result = await api("/api/webapp/support", {
      method: "POST",
      body: JSON.stringify({
        ...identityPayload(),
        message: input.value.trim(),
      }),
    });
    showNotice(`Support ticket #${result.ticket_id} ochildi.`);
    input.value = "";
  } catch (error) {
    showNotice(error.message);
  }
});
