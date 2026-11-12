// Поле ввода: Enter отправляет, Shift+Enter — перенос строки, высота растёт сама

export function setupComposer({ form, input, button, onSend }) {
  const autosize = () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 140) + 'px';
  };

  input.addEventListener('input', autosize);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = input.value;
    input.value = '';
    autosize();
    onSend(text);
  });

  return {
    setBusy: (busy) => { button.disabled = busy; },
    focus: () => input.focus(),
  };
}
