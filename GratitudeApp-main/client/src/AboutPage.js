const AboutPage = () => {
  return (
    <div className="page">
      <h1>About</h1>
      <p>
        This Gratitude &amp; Mood journal runs as a microservice playground: a
        React frontend, multiple Node.js services leveraging gRPC, and a shared
        Postgres database running inside Kubernetes.
      </p>
      <p>
        Log gratitude entries, track your mood, and watch weekly insights update
        in real time as the services talk to each other. It’s a compact but
        practical demo of cloud-native patterns you can actually use every day.
      </p>
    </div>
  );
};

export default AboutPage;
