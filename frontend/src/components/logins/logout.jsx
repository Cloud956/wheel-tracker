import Cookies from 'js-cookie';

function Logout({ onLogout }) {
    const handleLogout = () => {
      // Clear your app's auth state (token, cookie, user, etc.)
      Cookies.remove("token"); 
      console.log("Logout Success");
  
      // Optional: disable Google auto sign-in
      if (window.google) {
        google.accounts.id.disableAutoSelect();
      }

      if (onLogout) {
        onLogout();
      }
    };
  
    return (
      <button className="btn btn-logout" onClick={handleLogout}>
        Logout
      </button>
    );
  }
  
  export default Logout;
  