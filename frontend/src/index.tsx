import React from 'react';
import ReactDOM from 'react-dom/client';
import "normalize.css";
import "@blueprintjs/core/lib/css/blueprint.css";
import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';
import { BrowserRouter } from 'react-router-dom';
import { ApolloClient, ApolloProvider, InMemoryCache } from '@apollo/client';
import { CartProvider } from './context/CartContext';
import createUploadLink from 'apollo-upload-client/createUploadLink.mjs';
import { ToasterProvider } from './context/ToasterContext';
import { LoginStatusProvider } from './context/LoginStatusContext';
import { Worker } from '@react-pdf-viewer/core';

const client = new ApolloClient({
  cache: new InMemoryCache(),
  link: createUploadLink({
    uri: process.env.REACT_APP_BACKEND_URL,
  })
});

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);
root.render(
  <React.StrictMode>
    <BrowserRouter>
      <ApolloProvider client={client}>
        <CartProvider>
          <ToasterProvider>
            <LoginStatusProvider>
              <Worker workerUrl='/pdf.worker.min.js'>
                <App />
              </Worker>
            </LoginStatusProvider>
          </ToasterProvider>
        </CartProvider>
      </ApolloProvider>
    </BrowserRouter>
  </React.StrictMode>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();
