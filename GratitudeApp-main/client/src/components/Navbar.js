import { NavLink, Link } from "react-router-dom";
import "./Navbar.css";

const Navbar = () => {
  return (
    <header className="navbar">
      <div className="nav-inner">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden>
            ◼
          </span>
          Gratitude
        </Link>
        <nav className="nav-links" aria-label="Primary">
          <NavLink exact to="/" className="nav-link" activeClassName="active">
            Home
          </NavLink>
          <NavLink to="/about" className="nav-link" activeClassName="active">
            About
          </NavLink>
          <NavLink to="/contact" className="nav-link" activeClassName="active">
            Contact
          </NavLink>
          <NavLink to="/otherpage" className="nav-link" activeClassName="active">
            Other
          </NavLink>
        </nav>
      </div>
    </header>
  );
};

export default Navbar;
