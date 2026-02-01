import { useEffect } from "react";

const clientId =
  "992920333249-jl7q5rghgbb09g3r2mjdqgorho0bnjkb.apps.googleusercontent.com";

function Login() {
  useEffect(() => {
    /* global google */
    if (!window.google) return;

    google.accounts.id.initialize({
      client_id: clientId,
      callback: handleSuccess,
    });

    google.accounts.id.renderButton(
      document.getElementById("signInButton"),
      {
        theme: "outline",
        size: "large",
        text: "signin_with",
      }
    );

    // Optional: auto sign-in
    google.accounts.id.prompt();
  }, []);

  const handleSuccess = (response) => {
    console.log("Login Success (JWT):", response.credential);
    // Send response.credential to backend for verification
  };

  return <div id="signInButton"></div>;
}

export default Login;
