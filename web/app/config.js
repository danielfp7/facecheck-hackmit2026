// Where the FaceCheck server is, for a copy of these pages hosted somewhere else
// (Vercel). Leave empty when the server serves these files itself.
//
// This is a Cloudflare quick tunnel to the Mac running the server, so it changes every time
// the tunnel restarts. When it does, either redeploy with the new value or just open the
// site once as ?api=https://... and the browser remembers it.
window.FACECHECK_API = "https://disclaimer-protecting-talked-newcastle.trycloudflare.com";
