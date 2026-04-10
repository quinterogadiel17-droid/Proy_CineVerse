document.querySelectorAll('.flash').forEach(message => {
  setTimeout(() => {
    message.style.transition = 'opacity .4s ease, transform .4s ease';
    message.style.opacity = '0';
    message.style.transform = 'translateY(-4px)';
    setTimeout(() => message.remove(), 400);
  }, 4200);
});

document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', event => {
    if (event.target === overlay) overlay.classList.remove('open');
  });
});

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(modal => modal.classList.remove('open'));
  }
});

document.querySelectorAll('.js-city-select').forEach(select => {
  select.addEventListener('change', async event => {
    const cityId = event.target.value;
    const sedeTargetId = event.target.dataset.sedeTarget;
    const sedeSelect = document.getElementById(sedeTargetId);
    if (!sedeSelect || !cityId) return;

    try {
      const response = await fetch(`/api/ciudades/${cityId}/sedes`);
      const sedes = await response.json();
      sedeSelect.innerHTML = '<option value="">Todas las sedes</option>' +
        sedes.map(sede => `<option value="${sede.id}">${sede.nombre}</option>`).join('');
    } catch (error) {
      console.error(error);
    }
  });
});
