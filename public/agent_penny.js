// Chainlit accepts a single custom JavaScript entry point, so this file loads
// each independent frontend customization.
const SCRIPT_NAMES = ["mic_fix", "api_key_masking"];

for (const scriptName of SCRIPT_NAMES) {
  // Public assets are served from /public by Chainlit.
  const script = document.createElement("script");
  script.src = `/public/${scriptName}.js`;
  document.head.appendChild(script);
}
