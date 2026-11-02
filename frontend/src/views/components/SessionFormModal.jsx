import { useState } from "react";

function getInitialValues(session) {
  return {
    title: session?.title ?? "",
    location: session?.location === "Unknown location" ? "" : session?.location ?? "",
    notes: session?.notes ?? "",
  };
}

function validateForm(values) {
  if (!values.title.trim()) {
    return "Session name is required.";
  }

  if (!values.location.trim()) {
    return "Location is required.";
  }

  return "";
}

function parseValues(values) {
  return {
    title: values.title.trim(),
    location: values.location.trim(),
    notes: values.notes.trim(),
  };
}

export function SessionFormModal({ session, onClose, onSubmit }) {
  const [formValues, setFormValues] = useState(() => getInitialValues(session));
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  function updateField(field, value) {
    setFormValues((currentValues) => ({
      ...currentValues,
      [field]: value,
    }));
  }

  async function handleSubmit(event) {
    event.preventDefault();

    const validationMessage = validateForm(formValues);
    if (validationMessage) {
      setErrorMessage(validationMessage);
      return;
    }

    setErrorMessage("");
    setIsSubmitting(true);

    try {
      await onSubmit(parseValues(formValues));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Unable to save session.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="wizard-overlay" role="presentation">
      <section
        className="wizard-modal session-form-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="session-form-title"
      >
        <header className="wizard-header">
          <div>
            <h3 id="session-form-title">Edit session</h3>
          </div>
          <button type="button" className="ghost-button" onClick={onClose}>
            Cancel
          </button>
        </header>

        <form className="wizard-form" onSubmit={handleSubmit}>
          <div className="wizard-grid">
            <label className="wizard-field wizard-field--full">
              <span>Session name</span>
              <input
                type="text"
                value={formValues.title}
                onChange={(event) => updateField("title", event.target.value)}
              />
            </label>

            <label className="wizard-field wizard-field--full">
              <span>Location</span>
              <input
                type="text"
                value={formValues.location}
                onChange={(event) => updateField("location", event.target.value)}
              />
            </label>

            <label className="wizard-field wizard-field--full">
              <span>Notes</span>
              <textarea
                rows="5"
                value={formValues.notes}
                onChange={(event) => updateField("notes", event.target.value)}
              />
            </label>
          </div>

          {errorMessage && <p className="wizard-error">{errorMessage}</p>}

          <footer className="wizard-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button type="submit" className="primary-button" disabled={isSubmitting}>
              {isSubmitting ? "Saving..." : "Save session"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
