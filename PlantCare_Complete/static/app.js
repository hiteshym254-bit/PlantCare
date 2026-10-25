document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form[data-confirm]").forEach(form => {
    form.addEventListener("submit", event => {
      if (!window.confirm(form.dataset.confirm || "Are you sure?")) {
        event.preventDefault();
      }
    });
  });

  // Register the service worker for push messages.
  if (
    "serviceWorker" in navigator &&
    (location.protocol === "https:" ||
      location.hostname === "localhost" ||
      location.hostname === "127.0.0.1")
  ) {
    navigator.serviceWorker.register("/service-worker.js").catch(error => {
      console.error("PlantCare service worker registration failed:", error);
    });
  }

  const notifyButton = document.getElementById("notifyButton");

  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding)
      .replace(/-/g, "+")
      .replace(/_/g, "/");
    const rawData = window.atob(base64);
    const output = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; i += 1) {
      output[i] = rawData.charCodeAt(i);
    }

    return output;
  }

  async function readJsonResponse(response) {
    let result = {};
    try {
      result = await response.json();
    } catch (_) {
      // The server may return a non-JSON error page.
    }

    if (!response.ok) {
      throw new Error(
        result.error || ("Request failed (" + response.status + ").")
      );
    }

    return result;
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    return readJsonResponse(response);
  }

  async function getExistingSubscription() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      return null;
    }

    const registration = await navigator.serviceWorker.getRegistration("/");
    if (!registration) {
      return null;
    }

    return registration.pushManager.getSubscription();
  }

  if (notifyButton) {
    const pushSupported =
      "Notification" in window &&
      "serviceWorker" in navigator &&
      "PushManager" in window;

    if (!pushSupported) {
      notifyButton.textContent = "Notifications unavailable";
      notifyButton.disabled = true;
      notifyButton.title =
        "Use a browser that supports push notifications on a secure connection.";
    } else {
      notifyButton.textContent = "Enable notifications";

      if (Notification.permission === "granted") {
        getExistingSubscription()
          .then(subscription => {
            if (subscription) {
              notifyButton.textContent = "Send test notification";
            }
          })
          .catch(error => {
            console.warn("Could not check PlantCare subscription:", error);
          });
      }

      notifyButton.addEventListener("click", async () => {
        const originalText = notifyButton.textContent;
        notifyButton.disabled = true;
        notifyButton.textContent = "Setting up notifications…";

        try {
          if (Notification.permission !== "granted") {
            const permission = await Notification.requestPermission();
            if (permission !== "granted") {
              throw new Error(
                "Notifications were not allowed. Enable them in your browser's site settings and try again."
              );
            }
          }

          if (
            location.protocol !== "https:" &&
            location.hostname !== "localhost" &&
            location.hostname !== "127.0.0.1"
          ) {
            throw new Error("Push notifications require a secure HTTPS connection.");
          }

          const registration = await navigator.serviceWorker.register(
            "/service-worker.js"
          );
          await navigator.serviceWorker.ready;

          let subscription = await registration.pushManager.getSubscription();

          if (!subscription) {
            const keyResponse = await fetch("/api/push/public-key", {
              credentials: "same-origin"
            });
            const keyData = await readJsonResponse(keyResponse);

            if (!keyData.publicKey) {
              throw new Error("PlantCare's push notification key is missing.");
            }

            subscription = await registration.pushManager.subscribe({
              userVisibleOnly: true,
              applicationServerKey: urlBase64ToUint8Array(keyData.publicKey)
            });
          }

          await postJson("/api/push/subscribe", subscription.toJSON());

          notifyButton.textContent = "Sending test notification…";
          const testResult = await postJson("/api/push/test", {});

          notifyButton.textContent = "Send test notification";
          alert(
            testResult.message ||
            "PlantCare sent a test push notification. Check your device."
          );
        } catch (error) {
          console.error("PlantCare push notification setup failed:", error);
          notifyButton.textContent = originalText;
          alert(error.message || "Could not enable PlantCare push notifications.");
        } finally {
          notifyButton.disabled = false;
        }
      });
    }

    // This is a page-open reminder, separate from web-push delivery.
    if (
      "Notification" in window &&
      Notification.permission === "granted"
    ) {
      const dueCount = document.querySelectorAll(".reminder-item").length;

      if (dueCount > 0 && !sessionStorage.getItem("plantcare_due_notice")) {
        setTimeout(() => {
          new Notification("PlantCare watering reminder", {
            body: dueCount === 1
              ? "One plant needs watering."
              : (dueCount + " plants need watering."),
            icon: "/static/leaf.svg"
          });
          sessionStorage.setItem("plantcare_due_notice", "shown");
        }, 900);
      }
    }
  }
});
