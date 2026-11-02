import { useState } from "react";

function getInitialValues(boat) {
  return {
    name: boat?.name ?? "",
    className: boat?.className ?? "",
    sailNumber: boat?.sailNumber ?? "",
  };
}

function validateForm(values) {
  if (!values.name.trim()) {
    return "Boat name is required.";
  }

  if (!values.className.trim()) {
    return "Class name is required.";
  }

  if (!values.sailNumber.trim()) {
    return "Sail number is required.";
  }

  return "";
}

function parseValues(values) {
  return {
    name: values.name.trim(),
    className: values.className.trim(),
    sailNumber: values.sailNumber.trim(),
  };
}

export function BoatFormModal({ boat = null, mode = "create", onClose, onSubmit }) {
  const [formValues, setFormValues] = useState(() => getInitialValues(boat));
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const title = mode === "edit" ? "Edit boat" : "Add boat";

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
      setErrorMessage(error instanceof Error ? error.message : "Unable to save boat.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="wizard-overlay" role="presentation">
      <section
        className="wizard-modal boat-form-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="boat-form-title"
      >
        <header className="wizard-header">
          <div>
            <h3 id="boat-form-title">{title}</h3>
          </div>
          <button type="button" className="ghost-button" onClick={onClose}>
            Cancel
          </button>
        </header>

        <form className="wizard-form" onSubmit={handleSubmit}>
          <div className="wizard-grid">
            <label className="wizard-field wizard-field--full">
              <span>Boat name</span>
              <input
                type="text"
                value={formValues.name}
                onChange={(event) => updateField("name", event.target.value)}
              />
            </label>

            <label className="wizard-field">
              <span>Class</span>
              <input
                type="text"
                value={formValues.className}
                onChange={(event) => updateField("className", event.target.value)}
              />
            </label>

            <label className="wizard-field">
              <span>Sail number</span>
              <input
                type="text"
                value={formValues.sailNumber}
                onChange={(event) => updateField("sailNumber", event.target.value)}
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
              {isSubmitting ? "Saving..." : "Save boat"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
