import { Fragment } from "react";
import "./App.css";
import { BrowserRouter as Router, Route } from "react-router-dom";
import OtherPage from "./OtherPage";
import MainComponent from "./MainComponent";
import Navbar from "./components/Navbar";
import AboutPage from "./AboutPage";
import ContactPage from "./ContactPage";
import Footer from "./components/Footer";

function App() {
  return (
    <Router>
      <Fragment>
        <Navbar />
        <div className="main">
          <Route exact path="/" component={MainComponent} />
          <Route path="/about" component={AboutPage} />
          <Route path="/contact" component={ContactPage} />
          <Route path="/otherpage" component={OtherPage} />
        </div>
        <Footer />
      </Fragment>
    </Router>
  );
}

export default App;
