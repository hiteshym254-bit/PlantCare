document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form[data-confirm]").forEach(form => {
    form.addEventListener("submit", event => {
      if (!window.confirm(form.dataset.confirm || "Are you sure?")) event.preventDefault();
    });
  });

  const notifyButton = document.getElementById("notifyButton");
  if (notifyButton) {
    if (!("Notification" in window)) {
      notifyButton.textContent = "Notifications unavailable";
      notifyButton.disabled = true;
      notifyButton.title = "This browser does not support notifications.";
    } else if (Notification.permission === "granted") {
      notifyButton.textContent = "Notifications enabled ✓";
    }
    notifyButton.addEventListener("click", async () => {
      if (!("Notification" in window)) {
        alert("This browser does not support notifications.");
        return;
      }
      const permission = await Notification.requestPermission();
      if (permission === "granted") {
        new Notification("PlantCare", { body: "Notifications are enabled. Check your garden for watering reminders.", icon: "/static/leaf.svg" });
        notifyButton.textContent = "Notifications enabled ✓";
      } else {
        alert("Notifications were not enabled. You can change this in your browser's site settings.");
      }
    });

    // This reminder appears when the dashboard is open. It does not wake a closed app.
    if ("Notification" in window && Notification.permission === "granted") {
      const dueCount = document.querySelectorAll(".reminder-item").length;
      if (dueCount > 0 && !sessionStorage.getItem("plantcare_due_notice")) {
        setTimeout(() => {
          new Notification("PlantCare watering reminder", {
            body: dueCount === 1 ? "One plant needs watering." : `${dueCount} plants need watering.`,
            icon: "/static/leaf.svg"
          });
          sessionStorage.setItem("plantcare_due_notice", "shown");
        }, 900);
      }
    }
  }

  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {});
  }
});
