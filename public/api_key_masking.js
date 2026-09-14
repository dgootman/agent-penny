// Treat settings fields whose IDs end in "_api_key" as secrets. Chainlit
// renders these inputs dynamically and may reset their type during rerenders.
function isApiKeyInput(node) {
  return (
    node instanceof HTMLInputElement &&
    node.id.toLowerCase().endsWith("_api_key")
  );
}

function maskApiKeyInputs(root) {
  // Handle the root itself as well as matching inputs nested beneath it.
  if (isApiKeyInput(root) && root.type !== "password") {
    root.type = "password";
  }

  if (root.querySelectorAll) {
    for (const input of root.querySelectorAll("input[id]")) {
      if (isApiKeyInput(input) && input.type !== "password") {
        input.type = "password";
      }
    }
  }
}

function observeApiKeyInputs() {
  // Mask fields already present before watching for subsequent UI updates.
  maskApiKeyInputs(document);

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === "attributes") {
        maskApiKeyInputs(mutation.target);
      } else {
        for (const node of mutation.addedNodes) {
          if (node instanceof Element) {
            maskApiKeyInputs(node);
          }
        }
      }
    }
  });

  observer.observe(document.documentElement, {
    // Watch both newly rendered fields and existing fields whose type changes.
    attributeFilter: ["type"],
    attributes: true,
    childList: true,
    subtree: true,
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", observeApiKeyInputs, {
    once: true,
  });
} else {
  observeApiKeyInputs();
}
