(() => {
  if (window.__gelImagePickerInstalled) return;
  window.__gelImagePickerInstalled = true;
  let choosing = false;
  document.addEventListener("click", async (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || input.type !== "file" ||
        !input.closest('[data-testid="stFileUploader"]') ||
        !window.pywebview?.api?.choose_image) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (choosing || input.disabled) return;
    choosing = true;
    try {
      const selected = await window.pywebview.api.choose_image();
      if (!selected) return;
      if (selected.error) {
        window.alert(selected.error);
        return;
      }
      if (!input.isConnected) return;
      const bytes = Uint8Array.from(atob(selected.data), (character) => character.charCodeAt(0));
      const files = new DataTransfer();
      files.items.add(new File([bytes], selected.name, {type: selected.type}));
      input.files = files.files;
      input.dispatchEvent(new Event("change", {bubbles: true}));
    } catch (error) {
      console.error("Unable to upload the selected image", error);
      window.alert("The image could not be opened. Please choose it again.");
    } finally {
      choosing = false;
    }
  }, true);
})();
