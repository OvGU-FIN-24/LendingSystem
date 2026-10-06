import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLoginStatus } from "../../context/LoginStatusContext";
import { Orders } from "./orders";
import { Login } from "../login/Login";
import { gql, useMutation } from "@apollo/client";
import { useLoginStatusDispatcher } from "../../context/LoginStatusContext";
import { useLogout } from "../../hooks/user-helper";
import './Profile.css';

const CHANGE_PASSWORD = gql`
mutation updateUser($password: String, $currentPassword: String, $userId: String!){
  updateUser(password: $password, currentPassword: $currentPassword, userId: $userId){
    ok
    statusCode
    infoText
  }
}
`;

const CHANGE_ADRESS = gql`
mutation updateUser($street: String, $houseNumber: Int, $city: String, $postcode: Int, $userId: String!){
  updateUser(street: $street, houseNumber: $houseNumber, city: $city, postcode: $postcode, userId: $userId){
    ok
    statusCode
    infoText
  }
}
`;

const CHANGE_EMAIL = gql`
mutation updateUser($email: String, $currentPassword: String, $userId: String!){
  updateUser(email: $email, currentPassword: $currentPassword, userId: $userId){
    ok
    statusCode
    infoText
  }
}
`;


export function Profile() {
  const navigate = useNavigate();
  const loginStatus = useLoginStatus();
  const [logoutMutation] = useLogout();
  const [isModalOpen, setModalOpen] = useState(false);
  const [isPasswordModalOpen, setPasswordModalOpen] = useState(false);
  const [editField, setEditField] = useState<"email" | "address" | null>(null);
  const [newEmail, setNewEmail] = useState("");
  const setLoginAction = useLoginStatusDispatcher();
  const [changePassword] = useMutation(CHANGE_PASSWORD);
  const [currentPassword, setCurrentPassword] = useState('');
  const [password, setPassword] = useState('');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [city, setCity] = useState('');
  const [houseNumber, setHouseNumber] = useState('');
  const [street, setStreet] = useState('');
  const [postcode, setPostcode] = useState('');
  const [changeAdress] = useMutation(CHANGE_ADRESS);
  const [changeEmail] = useMutation(CHANGE_EMAIL);




  const handleAdressChange = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!street || !city || !houseNumber || !postcode) {
      setErrorMessage('Alle Felder müssen ausgefüllt werden!');
      return;
    }
    if (!loginStatus.loggedIn){
      return;
    }
    const id = loginStatus.user.id;
    try {
      const { data } = await changeAdress({
        variables: {
          userId: id,
          street: street,
          houseNumber: houseNumber,
          postcode: postcode,
          city: city,
        }
      });

      if (data?.updateUser?.ok) {
        setErrorMessage('');
        alert('Adressänderung erfolgreich!');
        setModalOpen(false);
        setStreet('');
        setCity('');
        setHouseNumber('');
        setPostcode('');
      } else {
        setErrorMessage(data?.updateUser?.infoText || 'Adressänderung fehlgeschlagen.');
      }
    } catch (error) {
      setErrorMessage('Fehler bei der Adressänderung. Bitte versuche es später erneut.');
    }
  };

  const handleEmailChange = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newEmail || !currentPassword) {
      setErrorMessage('Alle Felder müssen ausgefüllt werden!');
      return;
    }
    if (!loginStatus.loggedIn){
      return;
    }
    const id = loginStatus.user.id;
    try {
      const { data } = await changeEmail({
        variables: {
          userId: id,
          email: newEmail,
          currentPassword: currentPassword
        }
      });

      if (data?.updateUser?.ok) {
        setErrorMessage('');
        alert('Email erfolgreich geändert!');
        setModalOpen(false);
        setNewEmail('');
        setCurrentPassword('');
      } else {
        setErrorMessage(data?.updateUser?.infoText || 'Änderung der E-Mail fehlgeschlagen.');
      }
    } catch (error) {
      setErrorMessage('Fehler bei der Änderung der E-Mail. Bitte versuche es später erneut.');
    }
  };

  const handlePasswordChange = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!currentPassword || !password || !repeatPassword) {
      setErrorMessage('Alle Felder müssen ausgefüllt werden!');
      return;
    }
    if (password.length < 10) {
      setErrorMessage('Das Passwort muss mindestens 10 Zeichen lang sein');
      return;
    }

    if (password !== repeatPassword) {
      setErrorMessage('Die Passwörter stimmen nicht überein!');
      return;
    }
    if (!loginStatus.loggedIn){
      return;
    }
    const id = loginStatus.user.id;
    try {
      const { data } = await changePassword({
        variables: {
          userId: id,
          password: password,
          currentPassword: currentPassword
        }
      });

      if (data?.updateUser?.ok) {
        setErrorMessage('');
        alert('Passwortänderung erfolgreich!');
        setPasswordModalOpen(false);
        setCurrentPassword('');
        setPassword('');
        setRepeatPassword('');
      } else {
        setErrorMessage(data?.updateUser?.infoText || 'Passwortänderung fehlgeschlagen!');
      }
    } catch (error) {
      setErrorMessage('Fehler bei der Passwortänderung. Bitte versuche es später erneut.');
    }
  };

  const handleLogout = () => {
    setLoginAction({ type: "logout" });
    localStorage.removeItem("authToken");
    console.log("User logged out");
    navigate("/");
  };

  if (!loginStatus.loggedIn) {
    return <Login onClose={() => {}} />;
  }

  return (
    <div className="profile-container5">
      <h2>Nutzereinstellungen</h2>
      <div className="profile-details5">
        <p style={{ marginBottom: '20px' }}>
          Vorname: {loginStatus.user?.firstName || ""}
        </p>
        <p style={{ marginBottom: '25px' }}>
          Name: {loginStatus.user?.lastName || ""}
        </p>
        <p style={{ marginBottom: '20px' }}>
          Rolle: {loginStatus.user?.organizationInfoList?.length > 0
            ? Array.isArray(loginStatus.user?.organizationInfoList?.[0]?.rights)
  ? loginStatus.user.organizationInfoList[0].rights.join(", ")
  : loginStatus.user.organizationInfoList[0].rights || "keine Rechte"
            : "keine Organisation"}
        </p>
        <p>
          E-Mail: {loginStatus.user?.email || " "}
          <button onClick={() => { setModalOpen(true); setEditField("email"); }} className="edit-button5">
            ✎
          </button>
        </p>
        <p style={{ marginBottom: '20px' }}>
          Adresse: {loginStatus.user?.street && loginStatus.user?.houseNumber 
    ? `${loginStatus.user.street} ${loginStatus.user.houseNumber}, ${loginStatus.user.postcode} ${loginStatus.user.city}`
    : " "}
          <button onClick={() => { setModalOpen(true); setEditField("address"); }} className="edit-button5">
            ✎
          </button>
        </p>
        <p style={{ marginBottom: '20px' }}>
          Matrikelnummer: {loginStatus.user?.matricleNumber || ""}
        </p>
        <button style={{ marginBottom: '20px' }} onClick={() => setPasswordModalOpen(true)} className="logout-button5">Passwort ändern</button>
        <br></br>
        <button onClick={handleLogout} className="logout-button5">Logout</button>
      </div>
      

      {isModalOpen && (
        <div className="modal222">
          <div className="modal-content222">
            <h3>{editField === "email" ? "Email" : "Adresse"} bearbeiten</h3>
            {editField === "email" ? (
              <label>
                Email:
                <input 
                  type="email" 
                  value={newEmail}
                  placeholder={loginStatus.user?.email}
                  onChange={(e) => setNewEmail(e.target.value)} 
                />
                Aktuelles Passwort:
                <input
                  type="password"
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                />
              </label>
            ) : (
              <label>
                Straße:
                <input 
                style={{marginBottom:"10px"}}
                  type="text" 
                  value={street} 
                  placeholder={loginStatus.user?.street}
                  onChange={(e) => setStreet(e.target.value)} 
                />
                Hausnummer:
                <input 
                  style={{marginBottom:"10px"}}
                  type="text" 
                  value={houseNumber}
                  placeholder={loginStatus.user?.houseNumber}
                  onChange={(e) => setHouseNumber(e.target.value)} 
                />
                Ort:
                <input
                  style={{marginBottom:"10px"}}
                  type="text" 
                  value={city}
                  placeholder={loginStatus.user?.city}
                  onChange={(e) => setCity(e.target.value)} 
                />
                PLZ:
                <input 
                  style={{marginBottom:"10px"}}
                  type="text" 
                  value={postcode} 
                  placeholder={loginStatus.user?.postcode.toString()}
                  onChange={(e) => setPostcode(e.target.value)} 
                />
              </label>
            )}
            <br />
            {errorMessage && <p className="error-message">{errorMessage}</p>}
            <div className="modal-buttons">
              <button onClick={editField === "email" ? handleEmailChange : handleAdressChange}>Speichern</button>
              <button onClick ={() => {setModalOpen(false); setErrorMessage(""); setCurrentPassword("")}}>Abbrechen</button>
            </div>
          </div>
        </div>
      )}

      {isPasswordModalOpen && (
                <div className="modal222">
                <div className="modal-content222">
                  <h3>Passwort ändern</h3>
                  <label>
                    Aktuelles Passwort:
                    <input
                      type="password"
                      autoComplete="current-password"
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      placeholder="Aktuelles Passwort"
                    />
                  </label>
                  <br /><br />
                  <label>
                    Neues Passwort:
                    <input 
                      type="password" 
                      value={password} 
                      onChange={(e) => setPassword(e.target.value)} 
                      placeholder="Passwort"
                    />
                  </label>
                  <br /><br />
                  <label>
                    Passwort wiederholen:
                    <input 
                      type="password" 
                      value={repeatPassword} 
                      onChange={(e) => setRepeatPassword(e.target.value)} 
                      placeholder="Passwort"
                    />
                  </label>
                  {errorMessage && <p className="error-message">{errorMessage}</p>}
            <div className="modal-buttons">
              <button onClick={handlePasswordChange}>Bestätigen</button>
              <button onClick ={() => {setPasswordModalOpen(false); setErrorMessage(""); setCurrentPassword("")}}>Abbrechen</button>
            </div>
      </div>      </div>
      )}

      <Orders />
    </div>
  );
}
