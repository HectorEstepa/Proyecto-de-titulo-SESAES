export const environment = {
  apiUrl: window.location.hostname === 'localhost'
    ? 'http://localhost:8080'
    : 'https://sesaes-backend.onrender.com'
};