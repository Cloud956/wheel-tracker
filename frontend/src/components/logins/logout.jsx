function Logout() {
    const handleLogout = () => {
      // Clear your app's auth state (token, cookie, user, etc.)
      localStorage.removeItem("token"); // example
      console.log("Logout Success");
  
      // Optional: disable Google auto sign-in
      if (window.google) {
        google.accounts.id.disableAutoSelect();
      }
    };
  
    return (
      <button onClick={handleLogout}>
        Logout
      </button>
    );
  }
  
  export default Logout;
  