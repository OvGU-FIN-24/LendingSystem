import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { gql, useMutation } from "@apollo/client";
import './Login.css';

const CONFIRM_PASSWORD_RESET = gql`
mutation confirmPasswordReset($token: String!, $newPassword: String!) {
  confirmPasswordReset(token: $token, newPassword: $newPassword) {
    ok
    infoText
    statusCode
  }
}
`;

const MIN_PASSWORD_LENGTH = 10;

/**
 * Target of the emailed reset link (`/reset-password?token=...`): sets a new password.
 */
export function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const [password, setPassword] = useState('');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [done, setDone] = useState(false);
  const [confirmPasswordReset, { loading }] = useMutation(CONFIRM_PASSWORD_RESET);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (password.length < MIN_PASSWORD_LENGTH) {
      setErrorMessage(`Das Passwort muss mindestens ${MIN_PASSWORD_LENGTH} Zeichen lang sein`);
      return;
    }
    if (password !== repeatPassword) {
      setErrorMessage('Die Passwörter stimmen nicht überein!');
      return;
    }
    try {
      const { data } = await confirmPasswordReset({ variables: { token, newPassword: password } });
      if (data?.confirmPasswordReset?.ok) {
        setErrorMessage('');
        setDone(true);
      } else {
        setErrorMessage(data?.confirmPasswordReset?.infoText || 'Der Link ist ungültig oder abgelaufen.');
      }
    } catch {
      // network or server failure: the details are not useful to the user
      setErrorMessage('Fehler bei der Anfrage. Bitte versuche es später erneut.');
    }
  };

  if (!token) {
    return (
      <div className="login-container">
        <div className="login-form">
          <h2>Passwort zurücksetzen</h2>
          <p className="error-message">Der Link ist ungültig oder abgelaufen.</p>
          <p><Link to="/login">Zum Login</Link></p>
        </div>
      </div>
    );
  }

  if (done) {
    return (
      <div className="login-container">
        <div className="login-form">
          <h2>Passwort zurücksetzen</h2>
          <p>Ihr Passwort wurde geändert. Sie können sich jetzt mit dem neuen Passwort anmelden.</p>
          <p><Link to="/login">Zum Login</Link></p>
        </div>
      </div>
    );
  }

  return (
    <div className="login-container">
      <form className="login-form" onSubmit={handleSubmit}>
        <h2>Neues Passwort festlegen</h2>
        <div className="form-group">
          <label htmlFor="reset-password">Neues Passwort (mindestens {MIN_PASSWORD_LENGTH} Zeichen)</label>
          <input style={{width:'380px'}} type="password" id="reset-password" autoComplete="new-password"
            value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        <div className="form-group">
          <label htmlFor="reset-password-repeat">Neues Passwort wiederholen</label>
          <input style={{width:'380px'}} type="password" id="reset-password-repeat" autoComplete="new-password"
            value={repeatPassword} onChange={(e) => setRepeatPassword(e.target.value)} required />
        </div>
        {errorMessage && <p className="error-message">{errorMessage}</p>}
        <button type="submit" className="submit-button" disabled={loading}>Passwort speichern</button>
        <p><Link to="/login">Zum Login</Link></p>
      </form>
    </div>
  );
}
