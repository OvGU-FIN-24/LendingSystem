import { useState } from "react";
import { FaEye, FaEyeSlash } from 'react-icons/fa';
import './Login.css';
import { gql, useMutation } from "@apollo/client";
import { useLoginStatusDispatcher } from "../../context/LoginStatusContext";
import { startTransition } from "react";

interface LoginProps {onClose: () => void;}

const query = gql`
mutation Login($email: String!, $password: String!) {
  login(email: $email, password: $password) {
    ok,
    infoText
  }
}
`;

const REGISTER_MUTATION = gql`
  mutation createUser($city: String,
  $country: String,
  $email: String!,
  $firstName: String!,
  $houseNumber: Int,
  $lastName: String!,
  $matricleNumber: Int,
  $password: String!,
  $phoneNumber: Int,
  $postcode: Int,
  $street: String) {
  createUser(city: $city,
  country: $country,
  email: $email,
  firstName: $firstName,
  houseNumber: $houseNumber,
  lastName: $lastName,
  matricleNumber: $matricleNumber,
  password: $password,
  phoneNumber: $phoneNumber,
  postcode: $postcode,
  street: $street){
      ok
    infoText
    statusCode
    }
  }
`;

const REQUEST_PASSWORD_RESET = gql`
mutation requestPasswordReset($email: String!) {
  requestPasswordReset(email: $email) {
    ok
    infoText
    statusCode
  }
}
`;

export function Login(props: LoginProps) {
  const setLoginAction = useLoginStatusDispatcher();
  const [isLogin, setIsLogin] = useState(true);
  const [first_name, setFirstName] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [street, setStreet] = useState('');
  const [houseNumber, setHouseNumber] = useState('');
  const [city, setCity] = useState('');
  const [country, setCountry] = useState('Deutschland');
  const [postcode, setPostcode] = useState('');
  const [matricleNumber, setMatricleNumber] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [registerUser] = useMutation(REGISTER_MUTATION);
  const [isForgotPassword, setIsForgotPassword] = useState(false);
  const [requestPasswordReset] = useMutation(REQUEST_PASSWORD_RESET);



  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      const { data } = await login({
        variables: {
          email: email,
          password: password
        }
      });
  
      if (data?.login?.ok) {
        setLoginAction({ type: 'login' });
        setErrorMessage('');
        props.onClose(); // Close modal on successful login
      } else {
        setErrorMessage(data?.login?.infoText || 'Fehler beim Login!');
      }
    } catch (error) {
      setErrorMessage('Fehler bei der Anfrage. Bitte versuche es später erneut.');
    }
  };
  
  const handleResetPassword = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      const { data } = await requestPasswordReset({
        variables: {
          email: email,
        }
      });
  
      if (data?.requestPasswordReset?.ok) {
        setErrorMessage('');
        alert(data.requestPasswordReset.infoText || 'Wenn ein Konto existiert, wurde eine E-Mail versendet.');
        props.onClose();
      } else {
        setErrorMessage(data?.requestPasswordReset?.infoText || 'Fehler bei der Anfrage!');
      }
    } catch (error) {
      setErrorMessage('Fehler bei der Anfrage. Bitte versuche es später erneut.');
    }
  };


  const handleRegister = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!first_name || !name || !email || !street || !houseNumber || !postcode || !city || !matricleNumber ||!phoneNumber || !password || !repeatPassword) {
      setErrorMessage('Alle Felder müssen ausgefüllt werden!');
      return;
    }
    if(!email.endsWith("ovgu.de")){
      setErrorMessage("Die E-Mail-Adresse muss auf 'ovgu.de' enden.");
      return;
    }

    if (password !== repeatPassword) {
      setErrorMessage('Die Passwörter stimmen nicht überein!');
      return;
    }
    if (password.length < 10) {
      setErrorMessage('Das Passwort muss mindestens 10 Zeichen lang sein');
      return;
    }

    try {
      const { data } = await registerUser({
        variables: {
          firstName: first_name,
          lastName: name,
          email: email,
          street: street,
          houseNumber: houseNumber,
          postcode: postcode,
          city: city,
          country: country,
          matricleNumber: matricleNumber,
          phoneNumber: phoneNumber,
          password: password
        }
      });

      if (data?.createUser?.ok) {
        setErrorMessage('');
        alert('Registrierung erfolgreich! Bitte logge dich ein.');
        setIsLogin(true);
        setPassword('');
      } else {
        setErrorMessage(data?.createUser?.infoText || 'Registrierung fehlgeschlagen.');
      }
    } catch (error) {
      setErrorMessage('Fehler bei der Registrierung. Bitte versuche es später erneut.');
    }
  };

  const toggleForm = () => {
    setIsLogin(!isLogin);
    setFirstName('');
    setName('');
    setEmail('');
    setPassword('');
    setRepeatPassword('');
    setStreet('');
    setHouseNumber('');
    setCity('');
    setPostcode('');
    setMatricleNumber('');
    setPhoneNumber('');
    setShowPassword(false);
    setErrorMessage('');
  };

  const toggleShowPassword = () => {
    setShowPassword(!showPassword);
  };

  const handleForgotPassword = () => {
    setIsForgotPassword(true);
  };
  

  const [login] = useMutation(query);

  return (
    <div className="login-container">
      {isLogin ? (
        
        <form className="login-form" onSubmit={handleLogin}>
          <h2>Login</h2>
          <div className="form-group">
            <label htmlFor="login-email">E-Mail-Adresse</label>
            <input style={{width:'380px'}}type="text" id="login-email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="form-group">
            <label htmlFor="login-password">Passwort</label>
            <div className="password-container">
              <input style={{width:'380px'}} type={showPassword ? "text" : "password"} id="login-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
              <span className="password-toggle" style={{marginTop:"8px"}} onClick={toggleShowPassword}>{showPassword ? <FaEye /> : <FaEyeSlash />}</span>
            </div>
          </div>
          {errorMessage && <p className="error-message">{errorMessage}</p>}
          <button type="submit" className="submit-button">Login</button>
          <p><button type="button" onClick={handleForgotPassword} className="forgot-password">Passwort vergessen?</button></p>

          <p>Kein Konto? <button type="button" onClick={toggleForm}>Registrieren</button></p>
        </form>
      ) : (
<form className="register-form" onSubmit={handleRegister}>
  <h2>Registrieren</h2>
  <div className="form-grid">
    <div className="form-column" style={{marginRight:"20px"}}>
      <div className="form-group"><label>Vorname</label><input type="text" value={first_name} onChange={(e) => setFirstName(e.target.value)} required /></div>
      <div className="form-group"><label>Name</label><input type="text" value={name} onChange={(e) => setName(e.target.value)} required /></div>
      <div className="form-group"><label>E-Mail-Adresse</label><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
      <div className="form-group"><label>Straße</label><input type="text" value={street} onChange={(e) => setStreet(e.target.value)} required /></div>
      <div className="form-group"><label>Hausnummer</label><input type="text" value={houseNumber} onChange={(e) => setHouseNumber(e.target.value)} required /></div>
      <div className="form-group"><label>Passwort</label><input type={showPassword ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
    </div>

    <div className="form-column" style={{marginRight:"20px"}}>
      <div className="form-group"><label>Ort</label><input type="text" value={city} onChange={(e) => setCity(e.target.value)} required /></div>
      <div className="form-group"><label>Postleitzahl</label><input type="text" value={postcode} onChange={(e) => setPostcode(e.target.value)} required /></div>
      <div className="form-group"><label>Land</label><input type="text" value={country} onChange={(e) => setCountry(e.target.value)} required /></div>
      <div className="form-group"><label>Matrikelnummer</label><input type="text" value={matricleNumber} onChange={(e) => setMatricleNumber(e.target.value)} required /></div>
      <div className="form-group"><label>Telefonnummer</label><input type="text" value={phoneNumber} onChange={(e) => setPhoneNumber(e.target.value)} required /></div>
      <div className="form-group"><label>Passwort wiederholen</label><input type={showPassword ? "text" : "password"} value={repeatPassword} onChange={(e) => setRepeatPassword(e.target.value)} required /></div>
    </div>
  </div>

  {errorMessage && <p className="error-message">{errorMessage}</p>}
  <button type="submit" className="submit-button">Registrieren</button>
  <p>Bereits registriert? <button type="button" onClick={toggleForm}>Zum Login</button></p>
</form>

      )}
      {isForgotPassword && (
        <div className="modal2222">
          <div className="modal-content2222">
          <h3 style={{textAlign: "center", marginTop: "60px"}}>{"Passwort vergessen"}</h3>            
          <p style={{ marginBottom: "20px", textAlign: "center", color: "#555" }}>
      Wenn ein Konto mit dieser E-Mail-Adresse existiert, erhalten Sie eine E-Mail mit einem Link,
      über den Sie ein neues Passwort festlegen können. Der Link ist eine Stunde gültig.
    </p>

    <label style={{ marginTop: "40px", display: "block" }}>
              Email-Adresse:
              <input 
              className="input2"
                type="email" 
                value={email} 
                onChange={(e) => {
                  const email = e.target.value;
                  startTransition(() => {
                    setEmail(email);
                  });
                }}  
                placeholder="Email des Kontos angeben"
                style={{
                  display: "block",
                  width: "385px", // Reduce width
                  padding: "8px",
                }}
              />
            </label>
            <br />
            {errorMessage && <p className="error-message">{errorMessage}</p>}
            <div className="modal-buttons">
              <button onClick={handleResetPassword}>Bestätigen</button>
              <button onClick={() => {setIsForgotPassword(false); setErrorMessage(""); setEmail("")}}>Abbrechen</button>
            </div>
          </div>
        </div>
      )

      }
    </div>
  );
}
