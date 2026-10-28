/**
 * MedTurnos Pro - Frontend Logic
 * Gestión de Turnos de Cuidadores y Actividades Médicas
 */

let fechaActual = new Date();
let cuadranteData = null;
let listaCuidadoresCache = [];
let listaMedicosCache = [];
let listaBloquesCache = [];
let listaActividadesCache = [];
let currentUserProfile = null;
let canvasPosterGlobal = null;

// Inicialización
document.addEventListener("DOMContentLoaded", async () => {
    actualizarInputFechaPicker(fechaActual);
    await checkAuth();
    await cargarDatosIniciales();
    await cargarCuadrante();
    await cargarActividades();
    await cargarMedicamentos();
});

// --- AUTENTICACIÓN Y SESIÓN ---
function getToken() {
    return localStorage.getItem("medturnos_token");
}

function setToken(token) {
    localStorage.setItem("medturnos_token", token);
}

function removeToken() {
    localStorage.removeItem("medturnos_token");
}

async function checkAuth() {
    const token = getToken();
    const adminBadge = document.getElementById("adminBadge");
    const adminUsername = document.getElementById("adminUsername");
    const adminQuickActions = document.getElementById("adminQuickActions");
    const loginBtn = document.getElementById("loginBtn");
    const loginBtnMobile = document.getElementById("loginBtnMobile");
    const btnNuevaAsignacion = document.getElementById("btnNuevaAsignacion");
    const btnNuevaActividad = document.getElementById("btnNuevaActividad");
    const btnGestionUsuarios = document.getElementById("btnGestionUsuarios");

    if (!token) {
        currentUserProfile = null;
        adminBadge.classList.add("hidden");
        adminBadge.classList.remove("flex");
        adminQuickActions.classList.add("hidden");
        adminQuickActions.classList.remove("flex");
        btnNuevaAsignacion.classList.add("hidden");
        btnNuevaAsignacion.classList.remove("inline-flex");
        btnNuevaActividad.classList.add("hidden");
        btnNuevaActividad.classList.remove("inline-flex");
        const btnNuevoTratamiento = document.getElementById("btnNuevoTratamiento");
        if (btnNuevoTratamiento) {
            btnNuevoTratamiento.classList.add("hidden");
            btnNuevoTratamiento.classList.remove("inline-flex");
        }
        if (btnGestionUsuarios) {
            btnGestionUsuarios.classList.add("hidden");
            btnGestionUsuarios.classList.remove("inline-flex");
        }
        const barraWhatsappSemanal = document.getElementById("barraWhatsappSemanal");
        if (barraWhatsappSemanal) {
            barraWhatsappSemanal.classList.add("hidden");
            barraWhatsappSemanal.classList.remove("flex");
        }
        const btnLogoutTop = document.getElementById("btnLogoutTop");
        if (btnLogoutTop) {
            btnLogoutTop.classList.add("hidden");
            btnLogoutTop.classList.remove("inline-flex");
        }
        if (loginBtn) loginBtn.classList.remove("hidden");
        if (loginBtnMobile) loginBtnMobile.classList.remove("hidden");
        return false;
    }

    try {
        const res = await fetch("/api/auth/me", {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) {
            const user = await res.json();
            currentUserProfile = user;
            const rolNorm = (user.rol || "").toLowerCase().trim();
            const esSuper = ["super_user", "super_admin", "superadmin"].includes(rolNorm);

            adminUsername.innerHTML = `
                <span class="flex items-center gap-1.5">
                    <i class="fa-solid ${esSuper ? 'fa-crown text-amber-500' : 'fa-shield text-blue-500'}"></i>
                    <span>${user.username}</span>
                    <span class="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded-full ${esSuper ? 'bg-purple-100 text-purple-800 border border-purple-200' : 'bg-blue-100 text-blue-800 border border-blue-200'}">
                        ${esSuper ? 'super_user' : 'admin'}
                    </span>
                </span>
            `;
            adminBadge.classList.remove("hidden");
            adminBadge.classList.add("flex");
            adminQuickActions.classList.remove("hidden");
            adminQuickActions.classList.add("flex");
            btnNuevaAsignacion.classList.remove("hidden");
            btnNuevaAsignacion.classList.add("inline-flex");
            btnNuevaActividad.classList.remove("hidden");
            btnNuevaActividad.classList.add("inline-flex");
            const btnNuevoTratamiento = document.getElementById("btnNuevoTratamiento");
            if (btnNuevoTratamiento) {
                btnNuevoTratamiento.classList.remove("hidden");
                btnNuevoTratamiento.classList.add("inline-flex");
            }

            // Mostrar botón WhatsApp semanal para usuarios autenticados
            const barraWhatsappSemanal = document.getElementById("barraWhatsappSemanal");
            if (barraWhatsappSemanal) {
                barraWhatsappSemanal.classList.remove("hidden");
                barraWhatsappSemanal.classList.add("flex");
            }

            // Visibilidad exclusiva de botones de usuarios: Solo Super Admin
            const btnNavUsuarios = document.getElementById("btnNavUsuarios");
            if (esSuper) {
                adminBadge.classList.add("cursor-pointer");
                adminBadge.title = "Click para gestionar Usuarios y Roles (Super Admin)";
                adminBadge.onclick = openUsuariosModal;
                if (btnNavUsuarios) {
                    btnNavUsuarios.classList.remove("hidden");
                    btnNavUsuarios.classList.add("inline-flex");
                }
                if (btnGestionUsuarios) {
                    btnGestionUsuarios.classList.remove("hidden");
                    btnGestionUsuarios.classList.add("inline-flex");
                }
            } else {
                adminBadge.classList.remove("cursor-pointer");
                adminBadge.title = "Sesión de Administrador";
                adminBadge.onclick = null;
                if (btnNavUsuarios) {
                    btnNavUsuarios.classList.add("hidden");
                    btnNavUsuarios.classList.remove("inline-flex");
                }
                if (btnGestionUsuarios) {
                    btnGestionUsuarios.classList.add("hidden");
                    btnGestionUsuarios.classList.remove("inline-flex");
                }
            }

            const btnLogoutTop = document.getElementById("btnLogoutTop");
            if (btnLogoutTop) {
                btnLogoutTop.classList.remove("hidden");
                btnLogoutTop.classList.add("inline-flex");
            }
            if (loginBtn) loginBtn.classList.add("hidden");
            if (loginBtnMobile) loginBtnMobile.classList.add("hidden");

            // Verificar si el usuario debe cambiar su contraseña (primer login)
            if (user.must_change_password) {
                openCambiarPasswordModal(true);
            }

            return true;
        } else {
            currentUserProfile = null;
            removeToken();
            return checkAuth();
        }
    } catch (e) {
        console.error("Error verificando sesión:", e);
        currentUserProfile = null;
        return false;
    }
}

async function handleLogin(e) {
    e.preventDefault();
    const user = document.getElementById("loginUsername").value.trim();
    const pass = document.getElementById("loginPassword").value.trim();
    const errorDiv = document.getElementById("loginError");

    errorDiv.classList.add("hidden");
    errorDiv.textContent = "";

    try {
        const res = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: user, password: pass })
        });
        const data = await res.json();
        if (res.ok) {
            setToken(data.access_token);
            closeLoginModal();
            await checkAuth();
            await cargarCuadrante();
            await cargarActividades();
        } else {
            errorDiv.textContent = data.detail || "Credenciales incorrectas";
            errorDiv.classList.remove("hidden");
        }
    } catch (err) {
        errorDiv.textContent = "Error de conexión";
        errorDiv.classList.remove("hidden");
    }
}

function logoutAdmin() {
    removeToken();
    window.location.reload();
}


// --- GESTIÓN DE FECHAS ---
function formatDateIso(dateObj) {
    const y = dateObj.getFullYear();
    const m = String(dateObj.getMonth() + 1).padStart(2, "0");
    const d = String(dateObj.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
}

function actualizarInputFechaPicker(dateObj) {
    const picker = document.getElementById("datePicker");
    picker.value = formatDateIso(dateObj);
}

function navegarSemana(diasOffset) {
    fechaActual.setDate(fechaActual.getDate() + diasOffset);
    actualizarInputFechaPicker(fechaActual);
    cargarCuadrante();
    cargarActividades();
    cargarMedicamentos();
}

function irSemanaActual() {
    fechaActual = new Date();
    actualizarInputFechaPicker(fechaActual);
    cargarCuadrante();
    cargarActividades();
    cargarMedicamentos();
}

function seleccionarFecha(valorStr) {
    if (valorStr) {
        const partes = valorStr.split("-");
        fechaActual = new Date(partes[0], partes[1] - 1, partes[2]);
        cargarCuadrante();
        cargarActividades();
        cargarMedicamentos();
    }
}


// --- CARGAR CUIDADORES, MÉDICOS Y BLOQUES ---
async function cargarDatosIniciales() {
    try {
        const [resC, resM, resB] = await Promise.all([
            fetch("/api/admin/cuidadores"),
            fetch("/api/admin/medicos"),
            fetch("/api/admin/bloques")
        ]);
        if (resC.ok) listaCuidadoresCache = await resC.json();
        if (resM.ok) listaMedicosCache = await resM.json();
        if (resB.ok) listaBloquesCache = await resB.json();
        poblarSelectsFormularios();
    } catch (e) {
        console.error("Error cargando cuidadores/médicos/bloques:", e);
    }
}

function poblarSelectsFormularios() {
    // 1. Select de CUIDADORES (Solo Cuidadores para Turnos)
    const selectCuid = document.getElementById("asigCuidador");
    selectCuid.innerHTML = listaCuidadoresCache
        .filter(c => c.activo)
        .map(c => `<option value="${c.id_cuidador}">${(c.nombre + (c.apellido ? ' ' + c.apellido : '')).trim()}</option>`)
        .join("");

    // 2. Select de BLOQUES en cuadrante (AM, PM1, PM2, Nocturno) - Solo nombres de bloque, sin horas
    const selectBloque = document.getElementById("asigBloque");
    selectBloque.innerHTML = listaBloquesCache.map(b => 
        `<option value="${b.id_bloque}">Bloque ${b.nombre_bloque}</option>`
    ).join("");

    // 3. Select de PERSONAL MÉDICO (Solo Personal Médico para Actividades Médicas)
    const actMed = document.getElementById("actMedico");
    actMed.innerHTML = `<option value="">-- Sin médico asignado (Opcional) --</option>` +
        listaMedicosCache
            .filter(m => m.activo)
            .map(m => `<option value="${m.id_medico}">${(m.nombre + (m.apellido ? ' ' + m.apellido : '')).trim()} (${m.especialidad})</option>`)
            .join("");
}

// Organizar automáticamente según las horas seleccionadas por el usuario
function autoSugerirBloque() {
    const horaIni = document.getElementById("asigHoraInicio").value;
    if (!horaIni) return;
    const [h, m] = horaIni.split(":").map(Number);
    const mins = h * 60 + m;

    let codigoSugerido = "AM";
    if (mins >= 360 && mins < 870) codigoSugerido = "AM";          // 06:00 a 14:29
    else if (mins >= 870 && mins < 1080) codigoSugerido = "PM1";   // 14:30 a 17:59
    else if (mins >= 1080 && mins < 1260) codigoSugerido = "PM2";  // 18:00 a 20:59
    else codigoSugerido = "N";                                     // 21:00 a 05:59

    const bloque = listaBloquesCache.find(b => b.codigo_bloque === codigoSugerido);
    if (bloque) {
        document.getElementById("asigBloque").value = bloque.id_bloque;
    }
}

// Si el usuario cambia el bloque manualmente, sugerir horario base del bloque
function alCambiarBloque() {
    const idBloque = parseInt(document.getElementById("asigBloque").value);
    const bloque = listaBloquesCache.find(b => b.id_bloque === idBloque);
    if (!bloque) return;

    const inicioInput = document.getElementById("asigHoraInicio");
    const finInput = document.getElementById("asigHoraFin");

    if (bloque.codigo_bloque === "AM") {
        inicioInput.value = "10:00";
        finInput.value = "14:30";
    } else if (bloque.codigo_bloque === "PM1") {
        inicioInput.value = "14:30";
        finInput.value = "18:00";
    } else if (bloque.codigo_bloque === "PM2") {
        inicioInput.value = "18:00";
        finInput.value = "21:00";
    } else if (bloque.codigo_bloque === "N") {
        inicioInput.value = "21:00";
        finInput.value = "10:00";
    }
}

// Gestión de cuidadores adicionales en la asignación de turnos (opcional)
function limpiarCuidadoresAdicionales() {
    const cont = document.getElementById("cuidadoresAdicionalesLista");
    if (cont) cont.innerHTML = "";
}

function agregarCampoCuidadorAdicional(idPreseleccionado = null) {
    const cont = document.getElementById("cuidadoresAdicionalesLista");
    if (!cont) return;

    const div = document.createElement("div");
    div.className = "flex items-center gap-2 animate-fadeIn";

    const optionsHtml = listaCuidadoresCache
        .filter(c => c.activo)
        .map(c => `<option value="${c.id_cuidador}" ${idPreseleccionado === c.id_cuidador ? 'selected' : ''}>${(c.nombre + (c.apellido ? ' ' + c.apellido : '')).trim()}</option>`)
        .join("");

    div.innerHTML = `
        <div class="flex-1">
            <select class="cuidador-adicional-select w-full px-3 py-2 text-sm border border-slate-200 rounded-xl focus:ring-2 focus:ring-brand-500 focus:outline-none bg-white">
                <option value="">-- Seleccionar Cuidador/a Adicional --</option>
                ${optionsHtml}
            </select>
        </div>
        <button type="button" onclick="this.closest('.flex').remove()" title="Quitar cuidador adicional" class="p-2 text-slate-400 hover:text-rose-600 rounded-xl hover:bg-rose-50 transition-colors">
            <i class="fa-solid fa-trash-can text-sm"></i>
        </button>
    `;

    cont.appendChild(div);
}


// --- CARGAR CUADRANTE SEMANAL ---
async function cargarCuadrante() {
    const fechaIso = formatDateIso(fechaActual);
    const tbody = document.getElementById("cuadranteBody");
    const esAdmin = !!getToken();

    try {
        const res = await fetch(`/api/public/cuadrante?fecha_base=${fechaIso}`);
        if (!res.ok) throw new Error("Error obteniendo datos del cuadrante");
        cuadranteData = await res.json();

        // 1. Rango de texto de la semana
        const ini = new Date(cuadranteData.inicio_semana + "T00:00:00");
        const fin = new Date(cuadranteData.fin_semana + "T00:00:00");
        const meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
        document.getElementById("rangoSemanaTexto").textContent = 
            `${ini.getDate()} ${meses[ini.getMonth()]} - ${fin.getDate()} ${meses[fin.getMonth()]} ${fin.getFullYear()}`;

        // 2. Encabezados de días
        cuadranteData.dias.forEach((dia, idx) => {
            const th = document.getElementById(`th-dia-${idx}`);
            const dObj = new Date(dia.fecha + "T00:00:00");
            const esHoyClass = dia.es_hoy ? "bg-brand-50 border-brand-200 text-brand-900 ring-2 ring-brand-400" : "";
            
            th.className = `p-3.5 text-center min-w-[150px] transition-all ${esHoyClass}`;
            th.innerHTML = `
                <div class="text-xs font-semibold uppercase tracking-wider text-slate-500">${dia.nombre}</div>
                <div class="text-sm font-bold text-slate-800">${dObj.getDate()} ${meses[dObj.getMonth()]}</div>
                ${dia.es_hoy ? '<span class="inline-block mt-1 px-2 py-0.5 text-[10px] bg-brand-600 text-white font-bold rounded-full">HOY</span>' : ''}
            `;
        });

        // 3. Renderizar Filas de Bloques (AM, PM1, PM2, Nocturno)
        tbody.innerHTML = "";
        cuadranteData.bloques.forEach(bloque => {
            const tr = document.createElement("tr");
            tr.className = "hover:bg-slate-50/70 transition-colors border-b border-slate-100";

            let bloqueBadgeColor = "bg-blue-50 text-blue-700 border-blue-200";
            if (bloque.codigo_bloque === "AM") bloqueBadgeColor = "bg-amber-50 text-amber-700 border-amber-200";
            else if (bloque.codigo_bloque === "PM1") bloqueBadgeColor = "bg-sky-50 text-sky-700 border-sky-200";
            else if (bloque.codigo_bloque === "PM2") bloqueBadgeColor = "bg-indigo-50 text-indigo-700 border-indigo-200";
            else if (bloque.codigo_bloque === "N") bloqueBadgeColor = "bg-purple-50 text-purple-700 border-purple-200";

            const tdBloque = document.createElement("td");
            tdBloque.className = "p-3 sm:p-4 align-middle sticky-col-cell border-r border-slate-200 text-center sm:text-left";
            tdBloque.innerHTML = `
                <div class="flex items-center space-x-2">
                    <span class="px-2.5 py-1 text-xs font-bold border rounded-lg uppercase tracking-wide ${bloqueBadgeColor}">${bloque.nombre_bloque}</span>
                </div>
            `;
            tr.appendChild(tdBloque);

            // 7 Días
            cuadranteData.dias.forEach(dia => {
                const td = document.createElement("td");
                td.className = `p-2.5 align-top border-r border-slate-100 min-w-[150px] ${dia.es_hoy ? 'bg-brand-50/20' : ''}`;

                let asigs = cuadranteData.matriz[bloque.id_bloque] && cuadranteData.matriz[bloque.id_bloque][dia.fecha];
                if (asigs && !Array.isArray(asigs)) {
                    asigs = [asigs];
                }

                if (asigs && asigs.length > 0) {
                    // Obtener horarios únicos asignados en este bloque
                    const horariosUnicos = [...new Set(asigs.map(a => a.horario_texto))].join(" / ");
                    const tieneReunionFamiliar = asigs.some(a => a.reunion_familiar);

                    td.innerHTML = `
                        <div class="p-2.5 rounded-xl border border-slate-200 bg-white shadow-sm hover:shadow-md transition-all space-y-2">
                            <!-- CABECERA DEL CUADRO: HORARIO ÚNICO Y CANTIDAD DE CUIDADORES -->
                            <div class="flex items-center justify-between gap-1 pb-1.5 border-b border-slate-100">
                                <div class="px-2 py-0.5 rounded bg-amber-50/90 border border-amber-200 text-amber-900 font-bold text-[11px] flex items-center gap-1">
                                    <i class="fa-solid fa-clock text-[10px]"></i>
                                    <span>${horariosUnicos}</span>
                                </div>
                                ${asigs.length > 1 ? `
                                    <span class="text-[10px] font-bold text-brand-700 bg-brand-50 border border-brand-200 px-1.5 py-0.5 rounded-full flex items-center gap-1" title="${asigs.length} cuidadores en este turno">
                                        <i class="fa-solid fa-users text-[9px]"></i>
                                        <span>${asigs.length}</span>
                                    </span>
                                ` : ''}
                            </div>

                            <!-- EVENTO ESPECIAL: REUNION FAMILIAR -->
                            ${tieneReunionFamiliar ? `
                                <div class="px-2 py-1 rounded-lg bg-amber-500 text-white font-extrabold text-[10px] tracking-wider uppercase text-center flex items-center justify-center gap-1.5 shadow-xs">
                                    <i class="fa-solid fa-users text-[10px]"></i>
                                    <span>REUNION FAMILIAR</span>
                                </div>
                            ` : ''}

                            <!-- LISTA DE CUIDADORES DENTRO DEL MISMO CUADRO -->
                            <div class="space-y-2 divide-y divide-slate-100">
                                ${asigs.map((asig, idx) => {
                                    let estadoHtml = '';
                                    if (asig.estado_notificacion === 'ENVIADO') {
                                        estadoHtml = `<span title="Notificado por WhatsApp" class="text-emerald-600 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded text-[10px] flex items-center gap-1 font-medium"><i class="fa-brands fa-whatsapp"></i> Enviado</span>`;
                                    } else if (asig.estado_notificacion === 'ERROR') {
                                        estadoHtml = `<span title="Error WhatsApp" class="text-rose-600 bg-rose-50 border border-rose-200 px-1.5 py-0.5 rounded text-[10px] flex items-center gap-1 font-medium"><i class="fa-solid fa-circle-exclamation"></i> Error</span>`;
                                    } else {
                                        estadoHtml = `<span title="Pendiente" class="text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded text-[10px] flex items-center gap-1 font-medium"><i class="fa-regular fa-clock"></i> Pendiente</span>`;
                                    }

                                    return `
                                        <div class="${idx > 0 ? 'pt-1.5' : ''} flex items-center justify-between gap-1.5">
                                            <span class="font-bold text-xs text-slate-900 leading-tight truncate">${asig.cuidador_nombre}</span>
                                            <div class="flex items-center gap-1.5 shrink-0">
                                                ${estadoHtml}
                                                ${esAdmin ? `
                                                    <button onclick="eliminarAsignacion(${asig.id_asignacion})" title="Desasignar cuidador" class="text-slate-300 hover:text-rose-600 transition-colors p-0.5">
                                                        <i class="fa-regular fa-trash-can text-xs"></i>
                                                    </button>
                                                ` : ''}
                                            </div>
                                        </div>
                                    `;
                                }).join("")}
                            </div>

                            <!-- BOTÓN PARA SUMAR OTRO CUIDADOR AL MISMO CUADRO (ADMIN) -->
                            ${esAdmin ? `
                                <div class="pt-1.5 border-t border-slate-100">
                                    <button onclick="prepararAsignacionDirecta('${dia.fecha}', ${bloque.id_bloque})" class="w-full py-1 text-[10px] font-semibold text-brand-600 hover:text-brand-700 bg-slate-50 hover:bg-brand-50 rounded-lg border border-dashed border-slate-200 hover:border-brand-300 transition-colors flex items-center justify-center gap-1">
                                        <i class="fa-solid fa-user-plus text-[9px]"></i>
                                        <span>+ Agregar cuidador</span>
                                    </button>
                                </div>
                            ` : ''}
                        </div>
                    `;
                } else {
                    if (esAdmin) {
                        td.innerHTML = `
                            <div onclick="prepararAsignacionDirecta('${dia.fecha}', ${bloque.id_bloque})" class="h-20 border-2 border-dashed border-slate-200 hover:border-brand-400 rounded-xl flex flex-col items-center justify-center text-slate-300 hover:text-brand-600 cursor-pointer transition-all bg-slate-50/40 hover:bg-brand-50/30">
                                <i class="fa-solid fa-plus text-xs mb-1"></i>
                                <span class="text-[11px] font-semibold">Asignar</span>
                            </div>
                        `;
                    } else {
                        td.innerHTML = `
                            <div class="h-20 rounded-xl flex items-center justify-center text-slate-300 text-xs italic bg-slate-50/30">
                                Sin Cuidador
                            </div>
                        `;
                    }
                }

                tr.appendChild(td);
            });

            tbody.appendChild(tr);
        });

    } catch (err) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="p-8 text-center text-rose-500">
                    <p>No se pudo cargar el cuadrante semanal.</p>
                </td>
            </tr>
        `;
    }
}


// --- CARGAR ACTIVIDADES MÉDICAS ---
async function cargarActividades() {
    const fechaIso = formatDateIso(fechaActual);
    const cont = document.getElementById("contenedorActividades");
    const esAdmin = !!getToken();

    try {
        const res = await fetch(`/api/public/actividades-semana?fecha_base=${fechaIso}`);
        if (!res.ok) throw new Error("Error obteniendo actividades");
        const actividades = await res.json();
        listaActividadesCache = Array.isArray(actividades) ? actividades : [];

        if (actividades.length === 0) {
            cont.innerHTML = `
                <div class="col-span-full text-center py-8 text-slate-400 bg-slate-50/70 rounded-xl border border-dashed border-slate-200">
                    <i class="fa-solid fa-clipboard-check text-2xl mb-2 text-slate-300"></i>
                    <p class="text-xs font-medium">No hay actividades ni visitas médicas programadas para esta semana.</p>
                </div>
            `;
            return;
        }

        cont.innerHTML = actividades.map(act => {
            const fechaObj = new Date(act.fecha + "T00:00:00");
            const diasSemana = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
            const diaSem = diasSemana[fechaObj.getDay()];
            const diaNum = fechaObj.getDate();
            const horaStr = act.hora ? act.hora.slice(0, 5) : "";

            const medicoNombre = act.medico_asignado 
                ? `${(act.medico_asignado.nombre + (act.medico_asignado.apellido ? ' ' + act.medico_asignado.apellido : '')).trim()} (${act.medico_asignado.especialidad})`
                : "Sin personal médico específico asignado";

            return `
                <div class="p-4 rounded-xl border border-slate-200 bg-white hover:border-teal-300 hover:shadow-md transition-all space-y-2.5">
                    <div class="flex items-center justify-between">
                        <span class="px-2 py-0.5 rounded-md bg-teal-50 border border-teal-200 text-teal-800 text-xs font-bold">
                            ${diaSem} ${diaNum} &bull; ${horaStr} hrs
                        </span>
                        ${esAdmin ? `
                            <div class="flex items-center space-x-1">
                                <button onclick="editarActividad(${JSON.stringify(act).replace(/"/g, '&quot;')})" title="Editar" class="p-1 text-slate-400 hover:text-teal-600">
                                    <i class="fa-regular fa-pen-to-square text-xs"></i>
                                </button>
                                <button onclick="eliminarActividad(${act.id_actividad})" title="Eliminar" class="p-1 text-slate-400 hover:text-rose-600">
                                    <i class="fa-regular fa-trash-can text-xs"></i>
                                </button>
                            </div>
                        ` : ''}
                    </div>

                    <h4 class="font-bold text-sm text-slate-900">${act.titulo}</h4>
                    
                    ${act.descripcion ? `<p class="text-xs text-slate-600 leading-relaxed">${act.descripcion}</p>` : ''}

                    <div class="pt-2 border-t border-slate-100 flex items-center space-x-2 text-xs ${act.medico_asignado ? 'text-teal-700 font-medium' : 'text-slate-400 italic'}">
                        <i class="fa-solid fa-user-doctor"></i>
                        <span class="truncate">${medicoNombre}</span>
                    </div>
                </div>
            `;
        }).join("");

    } catch (err) {
        cont.innerHTML = `<div class="col-span-full text-center py-6 text-rose-500 text-xs">Error cargando actividades médicas.</div>`;
    }
}


// --- ACCIONES ADMIN: ASIGNAR TURNO A CUIDADOR (CON HORAS 00:00 - 23:59 Y MÚLTIPLES CUIDADORES) ---
function openAsignacionModal() {
    document.getElementById("asigFecha").value = formatDateIso(fechaActual);
    document.getElementById("asigHoraInicio").value = "10:00";
    document.getElementById("asigHoraFin").value = "14:30";
    const chkReunion = document.getElementById("asigReunionFamiliar");
    if (chkReunion) chkReunion.checked = false;
    autoSugerirBloque();
    limpiarCuidadoresAdicionales();
    document.getElementById("asignacionModal").classList.remove("hidden");
}

function closeAsignacionModal() {
    limpiarCuidadoresAdicionales();
    const chkReunion = document.getElementById("asigReunionFamiliar");
    if (chkReunion) chkReunion.checked = false;
    document.getElementById("asignacionModal").classList.add("hidden");
}

function prepararAsignacionDirecta(fechaIso, idBloque) {
    document.getElementById("asigFecha").value = fechaIso;
    document.getElementById("asigBloque").value = idBloque;

    // Configurar horas de referencia según el bloque elegido
    const bloque = listaBloquesCache.find(b => b.id_bloque === idBloque);
    if (bloque) {
        if (bloque.codigo_bloque === "AM") {
            document.getElementById("asigHoraInicio").value = "10:00";
            document.getElementById("asigHoraFin").value = "14:30";
        } else if (bloque.codigo_bloque === "PM1") {
            document.getElementById("asigHoraInicio").value = "14:30";
            document.getElementById("asigHoraFin").value = "18:00";
        } else if (bloque.codigo_bloque === "PM2") {
            document.getElementById("asigHoraInicio").value = "18:00";
            document.getElementById("asigHoraFin").value = "21:00";
        } else if (bloque.codigo_bloque === "N") {
            document.getElementById("asigHoraInicio").value = "21:00";
            document.getElementById("asigHoraFin").value = "10:00";
        }
    }

    // Pre-cargar si el turno ya cuenta con reunión familiar
    let yaTieneReunion = false;
    if (cuadranteData && cuadranteData.matriz && cuadranteData.matriz[idBloque] && cuadranteData.matriz[idBloque][fechaIso]) {
        const as = cuadranteData.matriz[idBloque][fechaIso];
        if (Array.isArray(as) && as.some(a => a.reunion_familiar)) yaTieneReunion = true;
    }
    const chkReunion = document.getElementById("asigReunionFamiliar");
    if (chkReunion) chkReunion.checked = yaTieneReunion;

    limpiarCuidadoresAdicionales();
    document.getElementById("asignacionModal").classList.remove("hidden");
}

async function handleGuardarAsignacion(e) {
    e.preventDefault();
    const token = getToken();
    const fecha = document.getElementById("asigFecha").value;
    const id_cuidador_principal = parseInt(document.getElementById("asigCuidador").value);
    const hora_inicio = document.getElementById("asigHoraInicio").value;
    const hora_fin = document.getElementById("asigHoraFin").value;
    const id_bloque = parseInt(document.getElementById("asigBloque").value);
    const chkReunion = document.getElementById("asigReunionFamiliar");
    const reunion_familiar = chkReunion ? chkReunion.checked : false;

    // Recolectar cuidador principal y cuidadores adicionales (opcionales)
    const cuidadoresIds = [];
    if (id_cuidador_principal) {
        cuidadoresIds.push(id_cuidador_principal);
    }

    document.querySelectorAll(".cuidador-adicional-select").forEach(sel => {
        const val = parseInt(sel.value);
        if (val && !cuidadoresIds.includes(val)) {
            cuidadoresIds.push(val);
        }
    });

    if (cuidadoresIds.length === 0) {
        alert("Debes seleccionar al menos un/a cuidador/a.");
        return;
    }

    const payload = {
        fecha,
        id_cuidador: cuidadoresIds[0],
        cuidadores_ids: cuidadoresIds,
        hora_inicio: hora_inicio.length === 5 ? `${hora_inicio}:00` : hora_inicio,
        hora_fin: hora_fin.length === 5 ? `${hora_fin}:00` : hora_fin,
        id_bloque,
        reunion_familiar
    };

    try {
        const res = await fetch("/api/admin/asignaciones", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            closeAsignacionModal();
            cargarCuadrante();
        } else {
            const err = await res.json();
            alert(err.detail || "Error al asignar turno");
        }
    } catch (e) {
        alert("Error de conexión");
    }
}

async function eliminarAsignacion(idAsignacion) {
    if (!confirm("¿Deseas desasignar este turno de cuidador?")) return;
    const token = getToken();
    try {
        const res = await fetch(`/api/admin/asignaciones/${idAsignacion}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) {
            cargarCuadrante();
        } else {
            alert("No se pudo desasignar el turno");
        }
    } catch (e) {
        alert("Error de red");
    }
}


// --- ACCIONES ADMIN: ACTIVIDADES MÉDICAS ---
function openActividadModal() {
    document.getElementById("actividadModalTitle").textContent = "Programar Actividad Médica";
    document.getElementById("actId").value = "";
    document.getElementById("actFecha").value = formatDateIso(fechaActual);
    document.getElementById("actHora").value = "10:00";
    document.getElementById("actTitulo").value = "";
    document.getElementById("actDescripcion").value = "";
    document.getElementById("actMedico").value = "";
    document.getElementById("actividadModal").classList.remove("hidden");
}

function closeActividadModal() {
    document.getElementById("actividadModal").classList.add("hidden");
}

function editarActividad(act) {
    document.getElementById("actividadModalTitle").textContent = "Editar Actividad Médica";
    document.getElementById("actId").value = act.id_actividad;
    document.getElementById("actFecha").value = act.fecha;
    document.getElementById("actHora").value = act.hora ? act.hora.slice(0, 5) : "10:00";
    document.getElementById("actTitulo").value = act.titulo;
    document.getElementById("actDescripcion").value = act.descripcion || "";
    document.getElementById("actMedico").value = act.id_medico || "";
    document.getElementById("actividadModal").classList.remove("hidden");
}

async function handleGuardarActividad(e) {
    e.preventDefault();
    const token = getToken();
    const id = document.getElementById("actId").value;
    const fecha = document.getElementById("actFecha").value;
    const hora = document.getElementById("actHora").value;
    const titulo = document.getElementById("actTitulo").value.trim();
    const descripcion = document.getElementById("actDescripcion").value.trim();
    const medVal = document.getElementById("actMedico").value;
    const id_medico = medVal ? parseInt(medVal) : null;

    const payload = {
        fecha,
        hora: hora.length === 5 ? `${hora}:00` : hora,
        titulo,
        descripcion,
        id_medico
    };

    try {
        const url = id ? `/api/admin/actividades/${id}` : "/api/admin/actividades";
        const method = id ? "PUT" : "POST";

        const res = await fetch(url, {
            method,
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            closeActividadModal();
            cargarActividades();
        } else {
            const err = await res.json();
            alert(err.detail || "Error al guardar actividad");
        }
    } catch (e) {
        alert("Error de conexión");
    }
}

async function eliminarActividad(idActividad) {
    if (!confirm("¿Eliminar esta actividad médica?")) return;
    const token = getToken();
    try {
        const res = await fetch(`/api/admin/actividades/${idActividad}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) {
            cargarActividades();
        } else {
            alert("No se pudo eliminar la actividad");
        }
    } catch (e) {
        alert("Error de conexión");
    }
}


// --- ACCIONES ADMIN: GESTIÓN DE CUIDADORES ---
function openCuidadoresModal() {
    renderizarListaCuidadoresModal();
    document.getElementById("cuidadoresModal").classList.remove("hidden");
}

function closeCuidadoresModal() {
    document.getElementById("cuidadoresModal").classList.add("hidden");
}

function renderizarListaCuidadoresModal() {
    const cont = document.getElementById("listaCuidadores");
    if (listaCuidadoresCache.length === 0) {
        cont.innerHTML = `<p class="text-xs text-slate-400 py-4 text-center">No hay cuidadores registrados.</p>`;
        return;
    }

    const esSuper = currentUserProfile && (currentUserProfile.rol || "").toLowerCase() === "super_user";

    cont.innerHTML = listaCuidadoresCache.map(c => `
        <div class="flex items-center justify-between p-3 rounded-xl border border-slate-200 bg-white">
            <div>
                <div class="text-xs font-bold text-slate-900">${(c.nombre + (c.apellido ? ' ' + c.apellido : '')).trim()}</div>
                <div class="text-[11px] text-slate-500 font-mono flex flex-wrap items-center gap-2 mt-0.5">
                    <span class="flex items-center gap-1"><i class="fa-brands fa-whatsapp text-emerald-600"></i> ${c.telefono_whatsapp}</span>
                    ${c.mail ? `<span class="flex items-center gap-1 text-slate-600 font-sans"><i class="fa-solid fa-envelope text-sky-600"></i> ${c.mail}</span>` : `<span class="text-[10px] text-slate-400 italic">Sin correo</span>`}
                </div>
            </div>
            <div class="flex items-center space-x-1.5">
                <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${c.activo ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}">
                    ${c.activo ? 'Activo' : 'Inactivo'}
                </span>
                ${c.activo ? `
                    <button onclick="openEditarCuidadorModal(${c.id_cuidador})" title="Editar datos del cuidador/a" class="text-xs text-sky-600 hover:text-sky-800 p-1.5 rounded-lg hover:bg-sky-50 transition-colors">
                        <i class="fa-solid fa-pen-to-square"></i>
                    </button>
                    ${esSuper ? `
                        <button onclick="desactivarCuidador(${c.id_cuidador})" title="Desactivar cuidador (super_user)" class="text-xs text-rose-500 hover:text-rose-700 p-1.5 rounded-lg hover:bg-rose-50 transition-colors">
                            <i class="fa-solid fa-user-xmark"></i>
                        </button>
                    ` : `
                        <span title="Restricción: Solo super_user tiene permitido eliminar cuidadores" class="text-xs text-slate-300 p-1.5 cursor-not-allowed">
                            <i class="fa-solid fa-lock text-slate-400"></i>
                        </span>
                    `}
                ` : ''}
            </div>
        </div>
    `).join("");
}

async function handleCrearCuidador(e) {
    e.preventDefault();
    const token = getToken();
    const nombre = document.getElementById("cuidNombre").value.trim();
    const apellido = (document.getElementById("cuidApellido")?.value || "").trim();
    const numerosInput = document.getElementById("cuidTelefonoNumeros");
    const numeros = numerosInput ? numerosInput.value.trim() : "";
    const errorTel = document.getElementById("cuidTelefonoError");

    // Validar nombre
    if (!nombre) {
        alert("El nombre del cuidador/a es obligatorio.");
        return;
    }

    // Validar exactamente 8 dígitos numéricos
    if (!/^\d{8}$/.test(numeros)) {
        if (errorTel) errorTel.classList.remove("hidden");
        numerosInput?.focus();
        return;
    }
    if (errorTel) errorTel.classList.add("hidden");

    const telefono_whatsapp = "+569" + numeros;
    const mailInput = document.getElementById("cuidMail");
    const mail = mailInput && mailInput.value.trim() ? mailInput.value.trim() : null;

    try {
        const res = await fetch("/api/admin/cuidadores", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ nombre, apellido, telefono_whatsapp, mail, activo: true })
        });
        if (res.ok) {
            document.getElementById("nuevoCuidadorForm").reset();
            await cargarDatosIniciales();
            renderizarListaCuidadoresModal();
            cargarCuadrante();
        } else {
            const err = await res.json();
            alert(err.detail || "Error al agregar cuidador");
        }
    } catch (e) {
        alert("Error de conexión");
    }
}

async function desactivarCuidador(idCuidador) {
    const esSuper = currentUserProfile && (currentUserProfile.rol || "").toLowerCase() === "super_user";
    if (!esSuper) {
        alert("Restricción RBAC: Únicamente los usuarios con rol 'super_user' tienen autorización para eliminar o desactivar cuidadores.");
        return;
    }

    if (!confirm("¿Deseas desactivar a este cuidador?")) return;
    const token = getToken();
    try {
        const res = await fetch(`/api/admin/cuidadores/${idCuidador}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) {
            await cargarDatosIniciales();
            renderizarListaCuidadoresModal();
            cargarCuadrante();
        } else {
            const err = await res.json();
            alert(err.detail || "No se pudo desactivar el cuidador");
        }
    } catch (e) {
        alert("Error de conexión");
    }
}

function openEditarCuidadorModal(idCuidador) {
    const cuid = listaCuidadoresCache.find(c => c.id_cuidador === idCuidador);
    if (!cuid) {
        alert("Cuidador/a no encontrado/a");
        return;
    }

    document.getElementById("cuidEditId").value = cuid.id_cuidador;
    document.getElementById("cuidEditNombre").value = cuid.nombre || "";
    document.getElementById("cuidEditApellido").value = cuid.apellido || "";

    // Extraer los 8 dígitos tras +569 si existe
    let tel = (cuid.telefono_whatsapp || "").trim();
    if (tel.startsWith("+569")) {
        tel = tel.substring(4);
    } else if (tel.startsWith("569")) {
        tel = tel.substring(3);
    }
    document.getElementById("cuidEditTelefonoNumeros").value = tel.replace(/\D/g, '').slice(0, 8);
    const errTel = document.getElementById("cuidEditTelefonoError");
    if (errTel) errTel.classList.add("hidden");

    document.getElementById("cuidEditMail").value = cuid.mail || "";

    document.getElementById("editarCuidadorModal").classList.remove("hidden");
}

function closeEditarCuidadorModal() {
    const modal = document.getElementById("editarCuidadorModal");
    if (modal) modal.classList.add("hidden");
}

async function handleActualizarCuidador(e) {
    e.preventDefault();
    const token = getToken();
    const idCuidador = document.getElementById("cuidEditId").value;
    const nombre = document.getElementById("cuidEditNombre").value.trim();
    const apellido = (document.getElementById("cuidEditApellido")?.value || "").trim();
    const numerosInput = document.getElementById("cuidEditTelefonoNumeros");
    const numeros = numerosInput ? numerosInput.value.trim() : "";
    const errorTel = document.getElementById("cuidEditTelefonoError");

    if (!nombre) {
        alert("El nombre del cuidador/a es obligatorio.");
        return;
    }

    if (!/^\d{8}$/.test(numeros)) {
        if (errorTel) errorTel.classList.remove("hidden");
        numerosInput?.focus();
        return;
    }
    if (errorTel) errorTel.classList.add("hidden");

    const telefono_whatsapp = "+569" + numeros;
    const mailInput = document.getElementById("cuidEditMail");
    const mail = mailInput && mailInput.value.trim() ? mailInput.value.trim() : null;

    try {
        const res = await fetch(`/api/admin/cuidadores/${idCuidador}`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ nombre, apellido, telefono_whatsapp, mail })
        });
        if (res.ok) {
            closeEditarCuidadorModal();
            await cargarDatosIniciales();
            renderizarListaCuidadoresModal();
            cargarCuadrante();
            alert("¡Cuidador/a actualizado/a exitosamente!");
        } else {
            const err = await res.json();
            alert(err.detail || "Error al actualizar cuidador/a");
        }
    } catch (e) {
        alert("Error de conexión al actualizar cuidador/a");
    }
}


// --- ACCIONES ADMIN: GESTIÓN DE PERSONAL MÉDICO ---
function openMedicosModal() {
    renderizarListaMedicosModal();
    document.getElementById("medicosModal").classList.remove("hidden");
}

function closeMedicosModal() {
    document.getElementById("medicosModal").classList.add("hidden");
}

function renderizarListaMedicosModal() {
    const cont = document.getElementById("listaMedicos");
    if (listaMedicosCache.length === 0) {
        cont.innerHTML = `<p class="text-xs text-slate-400 py-4 text-center">No hay personal médico registrado.</p>`;
        return;
    }

    cont.innerHTML = listaMedicosCache.map(m => `
        <div class="flex items-center justify-between p-3 rounded-xl border border-teal-200 bg-white">
            <div>
                <div class="text-xs font-bold text-slate-900">${(m.nombre + (m.apellido ? ' ' + m.apellido : '')).trim()}</div>
                <div class="text-[11px] text-teal-700 font-medium">${m.especialidad}</div>
            </div>
            <div class="flex items-center space-x-2">
                <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${m.activo ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}">
                    ${m.activo ? 'Activo' : 'Inactivo'}
                </span>
                ${m.activo ? `
                    <button onclick="desactivarMedico(${m.id_medico})" title="Desactivar" class="text-xs text-rose-500 hover:text-rose-700 p-1">
                        <i class="fa-solid fa-user-xmark"></i>
                    </button>
                ` : ''}
            </div>
        </div>
    `).join("");
}

async function handleCrearMedico(e) {
    e.preventDefault();
    const token = getToken();
    const nombre = document.getElementById("medNombre").value.trim();
    const apellido = (document.getElementById("medApellido")?.value || "").trim();
    const especialidad = document.getElementById("medEspecialidad").value.trim();

    if (!nombre) {
        alert("El nombre es obligatorio");
        return;
    }
    if (!especialidad) {
        alert("La especialidad es obligatoria");
        return;
    }

    try {
        const res = await fetch("/api/admin/medicos", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ nombre, apellido, especialidad, activo: true })
        });
        if (res.ok) {
            document.getElementById("nuevoMedicoForm").reset();
            await cargarDatosIniciales();
            renderizarListaMedicosModal();
            cargarActividades();
        } else {
            const err = await res.json();
            alert(err.detail || "Error al registrar médico");
        }
    } catch (e) {
        alert("Error de conexión");
    }
}

async function desactivarMedico(idMedico) {
    if (!confirm("¿Desactivar este miembro del personal médico?")) return;
    const token = getToken();
    try {
        const res = await fetch(`/api/admin/medicos/${idMedico}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) {
            await cargarDatosIniciales();
            renderizarListaMedicosModal();
            cargarActividades();
        }
    } catch (e) {
        alert("Error de conexión");
    }
}


// --- ACCIONES ADMIN: WHATSAPP INDIVIDUAL ---
function formatFechaIsoVisual(fechaIso) {
    if (!fechaIso) return "";
    const partes = String(fechaIso).split("-");
    if (partes.length === 3) {
        return `${partes[2]}/${partes[1]}/${partes[0]}`;
    }
    return fechaIso;
}

async function openModalWhatsAppIndividual(rangoInicial = "semana") {
    const modal = document.getElementById("modalWhatsAppIndividual");
    if (!modal) return;

    // Asegurar que cuidadores estén cargados en cache
    if (!listaCuidadoresCache || listaCuidadoresCache.length === 0) {
        try {
            const resC = await fetch("/api/admin/cuidadores");
            if (resC.ok) listaCuidadoresCache = await resC.json();
        } catch (e) {
            console.error("Error al cargar lista de cuidadores:", e);
        }
    }

    // Asegurar que cuadrante esté cargado
    if (!cuadranteData) {
        try {
            await cargarCuadrante();
        } catch (e) {
            console.error("Error al cargar cuadrante:", e);
        }
    }

    // Poblar Selector de Integrantes
    const selIntegrante = document.getElementById("waIntegranteSelect");
    if (selIntegrante) {
        selIntegrante.innerHTML = '<option value="">-- Selecciona un integrante --</option>';
        const personas = (listaCuidadoresCache || []).filter(c => c.activo !== false);
        personas.forEach(c => {
            const nom = `${c.nombre} ${c.apellido || ''}`.trim();
            const tel = c.telefono_whatsapp ? c.telefono_whatsapp : "Sin teléfono";
            const opt = document.createElement("option");
            opt.value = c.id_cuidador;
            opt.textContent = `${nom} (${tel})`;
            selIntegrante.appendChild(opt);
        });
    }

    // Poblar Selector Secundario de Días de la Semana (Lunes a Domingo)
    const selDia = document.getElementById("waDiaSelect");
    if (selDia && cuadranteData && Array.isArray(cuadranteData.dias)) {
        selDia.innerHTML = "";
        const meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
        cuadranteData.dias.forEach(d => {
            const dObj = new Date(d.fecha + "T00:00:00");
            const diaVisual = `${d.nombre} ${dObj.getDate()} ${meses[dObj.getMonth()]}`;
            const opt = document.createElement("option");
            opt.value = d.fecha;
            opt.textContent = `${diaVisual}${d.es_hoy ? " (HOY)" : ""}`;
            if (d.es_hoy) opt.selected = true;
            selDia.appendChild(opt);
        });
    }

    // Establecer Rango inicial
    const selRango = document.getElementById("waRangoTiempoSelect");
    if (selRango) {
        selRango.value = rangoInicial === "dia" ? "dia" : "semana";
    }
    toggleWaRangoTiempo();

    modal.classList.remove("hidden");
}

function closeModalWhatsAppIndividual() {
    const modal = document.getElementById("modalWhatsAppIndividual");
    if (modal) modal.classList.add("hidden");
}

// Aliases para compatibilidad total con botones existentes
function openNotificacionModal() {
    openModalWhatsAppIndividual("dia");
}

function closeNotificacionModal() {
    closeModalWhatsAppIndividual();
}

function toggleWaRangoTiempo() {
    const selRango = document.getElementById("waRangoTiempoSelect");
    const containerDia = document.getElementById("waDiaEspecificoContainer");
    if (!selRango || !containerDia) return;

    if (selRango.value === "dia") {
        containerDia.classList.remove("hidden");
    } else {
        containerDia.classList.add("hidden");
    }
}

function generarYEnviarWAIndividual() {
    const selIntegrante = document.getElementById("waIntegranteSelect");
    const idCuidador = selIntegrante ? selIntegrante.value : "";
    if (!idCuidador) {
        alert("Por favor selecciona a un integrante de la lista.");
        return;
    }

    const cuid = (listaCuidadoresCache || []).find(c => String(c.id_cuidador) === String(idCuidador));
    if (!cuid) {
        alert("No se encontró la información del integrante seleccionado.");
        return;
    }

    const nombreCompleto = `${cuid.nombre} ${cuid.apellido || ''}`.trim();

    // Validar teléfono de WhatsApp
    const rawTel = (cuid.telefono_whatsapp || "").trim();
    let telLimpio = rawTel.replace(/[^0-9]/g, "");
    if (!telLimpio) {
        alert(`El integrante seleccionado (${nombreCompleto}) no tiene un número de WhatsApp registrado.`);
        return;
    }
    // Formato internacional wa.me (Chile +56)
    if (telLimpio.length === 9 && telLimpio.startsWith("9")) {
        telLimpio = "56" + telLimpio;
    }

    const selRango = document.getElementById("waRangoTiempoSelect");
    const rango = selRango ? selRango.value : "semana";

    if (!cuadranteData || !Array.isArray(cuadranteData.dias) || cuadranteData.dias.length === 0) {
        alert("No se tienen cargados los datos del horario de la semana.");
        return;
    }

    let diasTarget = [];
    let periodoTexto = "";
    if (rango === "dia") {
        const fechaElegida = document.getElementById("waDiaSelect")?.value;
        const diaObj = cuadranteData.dias.find(d => d.fecha === fechaElegida) || cuadranteData.dias[0];
        diasTarget = [diaObj];
        periodoTexto = `${diaObj.nombre} ${formatFechaIsoVisual(diaObj.fecha)}`;
    } else {
        diasTarget = cuadranteData.dias;
        periodoTexto = `Semana del ${formatFechaIsoVisual(cuadranteData.inicio_semana)} al ${formatFechaIsoVisual(cuadranteData.fin_semana)}`;
    }

    // 1. Filtrar TURNOS de la persona en el periodo
    const turnosEncontrados = [];
    const diasConTurnoFechas = new Set();
    const jornadasCuidadorPorDia = {};

    (cuadranteData.bloques || []).forEach(bloque => {
        diasTarget.forEach(d => {
            const asigs = cuadranteData.matriz?.[bloque.id_bloque]?.[d.fecha];
            if (asigs) {
                const listaAsigs = Array.isArray(asigs) ? asigs : [asigs];
                listaAsigs.forEach(asig => {
                    if (String(asig.id_cuidador) === String(idCuidador)) {
                        turnosEncontrados.push({
                            diaFecha: d.fecha,
                            diaNombre: d.nombre,
                            bloque: bloque.nombre_bloque,
                            hora_inicio: asig.hora_inicio,
                            hora_fin: asig.hora_fin,
                            horario_texto: asig.horario_texto || `${asig.hora_inicio} - ${asig.hora_fin}`,
                            reunion_familiar: !!asig.reunion_familiar
                        });
                        diasConTurnoFechas.add(d.fecha);
                        if (!jornadasCuidadorPorDia[d.fecha]) jornadasCuidadorPorDia[d.fecha] = [];
                        jornadasCuidadorPorDia[d.fecha].push({
                            hora_inicio: asig.hora_inicio,
                            hora_fin: asig.hora_fin
                        });
                    }
                });
            }
        });
    });

    // 2. Filtrar MEDICAMENTOS correspondientes en el periodo para sus jornadas
    const medicamentosEncontrados = [];
    const medicamentosVistos = new Set();

    diasTarget.forEach(d => {
        if (!diasConTurnoFechas.has(d.fecha)) return;
        const jornadas = jornadasCuidadorPorDia[d.fecha] || [];

        (listaTratamientosCache || []).forEach(trat => {
            if (!trat.dia_inicial || d.fecha < trat.dia_inicial) return;

            // Verificar si hay horarios explícitos para este día
            const explicit = (trat.horarios || []).filter(h => h.dia === d.fecha);
            let horasDelDia = [];
            if (explicit.length > 0) {
                horasDelDia = explicit.map(h => (h.hora || "").slice(0, 5)).filter(Boolean);
            } else {
                // Arrastrado: replicar horarios del día inicial o lista base
                const baseHoras = (trat.horarios || []).filter(h => h.dia === trat.dia_inicial);
                const source = baseHoras.length > 0 ? baseHoras : (trat.horarios || []);
                horasDelDia = Array.from(new Set(source.map(h => (h.hora || "").slice(0, 5)).filter(Boolean)));
            }

            if (horasDelDia.length > 0 && jornadas.length > 0) {
                const medKey = `${d.fecha}_${trat.nombre_medicamento}`;
                if (!medicamentosVistos.has(medKey)) {
                    medicamentosVistos.add(medKey);
                    const nomMed = trat.personal_medico
                        ? `${trat.personal_medico.nombre} ${trat.personal_medico.apellido || ''}`.trim()
                        : "";
                    medicamentosEncontrados.push({
                        diaFecha: d.fecha,
                        diaNombre: d.nombre,
                        nombre: trat.nombre_medicamento,
                        horas: horasDelDia.sort(),
                        medico: nomMed
                    });
                }
            }
        });
    });

    // 3. Filtrar ACTIVIDADES MÉDICAS correspondientes en el periodo para sus jornadas
    const actividadesEncontradas = [];
    const actividadesVistas = new Set();

    diasTarget.forEach(d => {
        if (!diasConTurnoFechas.has(d.fecha)) return;

        (listaActividadesCache || []).forEach(act => {
            if (act.fecha !== d.fecha) return;
            const actKey = `${d.fecha}_${act.titulo}_${act.hora}`;
            if (!actividadesVistas.has(actKey)) {
                actividadesVistas.add(actKey);
                const nomMed = act.medico_asignado
                    ? `${act.medico_asignado.nombre} ${act.medico_asignado.apellido || ''}`.trim()
                    : "";
                actividadesEncontradas.push({
                    diaFecha: d.fecha,
                    diaNombre: d.nombre,
                    titulo: act.titulo,
                    hora: (act.hora || "").slice(0, 5),
                    medico: nomMed,
                    descripcion: (act.descripcion || "").trim()
                });
            }
        });
    });

    // VALIDACIÓN: Detener si no tiene registros asignados en ese periodo
    if (turnosEncontrados.length === 0) {
        alert(`La persona seleccionada (${nombreCompleto}) no tiene turnos ni registros asignados para ${periodoTexto}.`);
        return;
    }

    // Ordenar turnos cronológicamente
    turnosEncontrados.sort((a, b) => a.diaFecha.localeCompare(b.diaFecha) || a.hora_inicio.localeCompare(b.hora_inicio));

    // REDACTAR MENSAJE ESTRUCTURADO CON EMOJIS
    let msg = `🏥 *RESUMEN DE TURNOS Y CUIDADOS*\n`;
    msg += `👤 *Integrante:* ${nombreCompleto}\n`;
    msg += `📅 *Periodo:* ${periodoTexto}\n\n`;

    // 🏥 SUS TURNOS
    msg += `🏥 *SUS TURNOS:*\n`;
    turnosEncontrados.forEach((t, i) => {
        const rf = t.reunion_familiar ? " *[REUNIÓN FAMILIAR]*" : "";
        msg += `  ${i + 1}. *${t.diaNombre} ${formatFechaIsoVisual(t.diaFecha)}*: Bloque *${t.bloque}* (${t.horario_texto} hrs)${rf}\n`;
    });
    msg += `\n`;

    // 💊 SUS MEDICAMENTOS (FORMATO DIARIO ORGANIZADO)
    msg += `💊 *SUS MEDICAMENTOS:*\n`;
    if (medicamentosEncontrados.length > 0) {
        // Agrupar cronológicamente por día
        const medsPorDiaMap = {};
        medicamentosEncontrados.forEach(m => {
            if (!medsPorDiaMap[m.diaFecha]) medsPorDiaMap[m.diaFecha] = [];
            medsPorDiaMap[m.diaFecha].push(m);
        });

        const diasOrdenados = Object.keys(medsPorDiaMap).sort();
        diasOrdenados.forEach(fStr => {
            const listaM = medsPorDiaMap[fStr];
            const dObj = (cuadranteData?.dias || []).find(d => d.fecha === fStr) || { nombre: listaM[0]?.diaNombre || "", fecha: fStr };
            msg += `\n📅 *${dObj.nombre} (${formatFechaIsoVisual(fStr)}):*\n`;
            listaM.forEach((m, i) => {
                const horasStr = m.horas.join(", ");
                const medInfo = m.medico ? ` _(Indicado por: ${m.medico})_` : "";
                msg += `  ${i + 1}. *${m.nombre}*: ${horasStr} hrs${medInfo}\n`;
            });
        });
    } else {
        msg += `  • No tienes administración de medicamentos programada para tu jornada.\n`;
    }
    msg += `\n`;

    // 📝 SUS ACTIVIDADES
    msg += `📝 *SUS ACTIVIDADES:*\n`;
    if (actividadesEncontradas.length > 0) {
        actividadesEncontradas.sort((a, b) => a.diaFecha.localeCompare(b.diaFecha) || a.hora.localeCompare(b.hora));
        actividadesEncontradas.forEach((a, i) => {
            const horaStr = a.hora ? `${a.hora} hrs` : "";
            const medInfo = a.medico ? ` _(A cargo: ${a.medico})_` : "";
            const descInfo = a.descripcion ? ` - ${a.descripcion}` : "";
            const diaInfo = rango === "semana" ? ` (${a.diaNombre})` : "";
            msg += `  ${i + 1}. *${a.titulo}*${diaInfo}: ${horaStr}${medInfo}${descInfo}\n`;
        });
    } else {
        msg += `  • No tienes actividades médicas programadas en tu horario de turno.\n`;
    }
    msg += `\n`;

    msg += `_Por favor confirma la recepción de este resumen. ¡Buen turno!_`;

    // ABRIR ENLACE DE WHATSAPP
    const urlWA = `https://wa.me/${telLimpio}?text=${encodeURIComponent(msg)}`;
    window.open(urlWA, "_blank");

    closeModalWhatsAppIndividual();
}

// --- MODAL LOGIN HELPER ---
function openLoginModal() {
    document.getElementById("loginModal").classList.remove("hidden");
}

function closeLoginModal() {
    document.getElementById("loginModal").classList.add("hidden");
}


// --- ACCIONES ADMIN: GESTIÓN DE USUARIOS Y ROLES (RBAC EXCLUSIVO SUPER ADMIN) ---
async function openUsuariosModal() {
    // Si aún no tenemos perfil en memoria, consultar /api/auth/me
    if (!currentUserProfile) {
        const token = getToken();
        if (token) {
            try {
                const res = await fetch("/api/auth/me", {
                    headers: { "Authorization": `Bearer ${token}` }
                });
                if (res.ok) {
                    currentUserProfile = await res.json();
                }
            } catch (err) {
                console.error("Error al obtener perfil para usuariosModal:", err);
            }
        }
    }

    const rolNorm = ((currentUserProfile && currentUserProfile.rol) || "").toLowerCase().trim();
    const esSuper = ["super_user", "super_admin", "superadmin"].includes(rolNorm);
    if (!esSuper) {
        alert("Acceso restringido: Solo el Super Admin tiene autorización para gestionar, crear, ver o eliminar usuarios.");
        return;
    }

    const modal = document.getElementById("usuariosModal");
    if (!modal) return;
    modal.classList.remove("hidden");

    actualizarInfoSesionUsuariosModal();
    await cargarUsuariosModal();
}

function closeUsuariosModal() {
    const modal = document.getElementById("usuariosModal");
    if (modal) modal.classList.add("hidden");
    const form = document.getElementById("nuevoUsuarioForm");
    if (form) form.reset();
    const msgDiv = document.getElementById("usuarioFormMsg");
    if (msgDiv) {
        msgDiv.className = "text-xs hidden font-medium p-2 rounded-lg";
        msgDiv.textContent = "";
    }
}

function actualizarInfoSesionUsuariosModal() {
    const sesionNombre = document.getElementById("usrSesionNombre");
    const sesionBadge = document.getElementById("usrSesionBadge");
    const optSuperUser = document.getElementById("optSuperUser");
    const avisoJerarquia = document.getElementById("avisoJerarquiaRol");

    if (!currentUserProfile) {
        if (sesionNombre) sesionNombre.textContent = "Super Admin";
        return;
    }

    if (sesionNombre) sesionNombre.textContent = currentUserProfile.username;

    if (sesionBadge) {
        sesionBadge.innerHTML = `
            <span class="inline-flex items-center gap-1 bg-purple-100 text-purple-800 border border-purple-200 px-2.5 py-0.5 rounded-full font-bold">
                <i class="fa-solid fa-crown text-amber-500"></i> super_user (Acceso Total Exclusivo)
            </span>
        `;
    }

    if (optSuperUser) {
        optSuperUser.disabled = false;
        optSuperUser.hidden = false;
        optSuperUser.textContent = "Superusuario (super_user)";
    }
    if (avisoJerarquia) {
        avisoJerarquia.classList.add("hidden");
    }
}

async function cargarUsuariosModal() {
    const cont = document.getElementById("listaUsuarios");
    if (!cont) return;
    const token = getToken();
    cont.innerHTML = `<p class="text-xs text-slate-400 py-3 text-center"><i class="fa-solid fa-spinner animate-spin mr-1"></i> Cargando usuarios...</p>`;

    try {
        const res = await fetch("/api/admin/usuarios", {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (!res.ok) {
            cont.innerHTML = `<p class="text-xs text-rose-500 py-3 text-center">No autorizado o error al consultar usuarios.</p>`;
            return;
        }
        const usuarios = await res.json();
        if (usuarios.length === 0) {
            cont.innerHTML = `<p class="text-xs text-slate-400 py-3 text-center">No hay usuarios registrados.</p>`;
            return;
        }

        const esSuper = currentUserProfile && (currentUserProfile.rol || "").toLowerCase() === "super_user";

        cont.innerHTML = usuarios.map(u => {
            const uEsSuper = (u.rol || "").toLowerCase() === "super_user";
            const esMismo = currentUserProfile && u.id_usuario === currentUserProfile.id_usuario;

            return `
                <div class="flex items-center justify-between p-3 rounded-xl border border-slate-200 bg-white shadow-xs">
                    <div class="flex items-center space-x-3">
                        <div class="w-8 h-8 rounded-lg ${uEsSuper ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'} flex items-center justify-center font-bold text-xs">
                            <i class="fa-solid ${uEsSuper ? 'fa-crown text-amber-500' : 'fa-shield'}"></i>
                        </div>
                        <div>
                            <div class="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                                <span>${u.username}</span>
                                ${esMismo ? '<span class="text-[10px] text-slate-400 font-normal">(Tu cuenta actual)</span>' : ''}
                            </div>
                            <div class="text-[11px] text-slate-500">ID #${u.id_usuario}</div>
                        </div>
                    </div>

                    <div class="flex items-center space-x-3">
                        <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold ${uEsSuper ? 'bg-purple-100 text-purple-800 border border-purple-200' : 'bg-blue-100 text-blue-800 border border-blue-200'}">
                            <i class="fa-solid ${uEsSuper ? 'fa-crown text-amber-500' : 'fa-shield text-blue-500'} text-[10px]"></i>
                            ${u.rol}
                        </span>

                        ${(esSuper && !esMismo) ? `
                            <button onclick="eliminarUsuario(${u.id_usuario}, '${u.username}')" title="Eliminar usuario" class="text-xs text-rose-500 hover:text-rose-700 p-1.5 rounded hover:bg-rose-50 transition-colors">
                                <i class="fa-solid fa-trash-can"></i>
                            </button>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join("");

    } catch (e) {
        cont.innerHTML = `<p class="text-xs text-rose-500 py-3 text-center">Error de red al consultar usuarios.</p>`;
    }
}

async function handleCrearUsuario(e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }

    const token = getToken();
    if (!token) {
        alert("Tu sesión ha expirado o no estás autenticado. Por favor inicia sesión nuevamente.");
        openLoginModal();
        return;
    }

    const usernameInput = document.getElementById("usrUsername");
    const passwordInput = document.getElementById("usrPassword");
    const rolInput = document.getElementById("usrRol");
    const btnSubmit = document.getElementById("btnCrearUsuario");
    const msgDiv = document.getElementById("usuarioFormMsg");

    const username = usernameInput ? usernameInput.value.trim() : "";
    const password = passwordInput ? passwordInput.value.trim() : "";
    const rol = rolInput ? rolInput.value : "admin";

    if (!username) {
        alert("Por favor ingresa un nombre de usuario.");
        if (usernameInput) usernameInput.focus();
        return;
    }

    if (!password || password.length < 4) {
        alert("La contraseña debe tener al menos 4 caracteres.");
        if (passwordInput) passwordInput.focus();
        return;
    }

    // Efecto de carga en botón
    const origBtnHtml = btnSubmit ? btnSubmit.innerHTML : "";
    if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Registrando...`;
    }

    if (msgDiv) {
        msgDiv.className = "text-xs hidden font-medium p-2 rounded-lg";
        msgDiv.textContent = "";
    }

    try {
        const res = await fetch("/api/admin/usuarios", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ username, password, rol })
        });

        const data = await res.json();

        if (res.ok) {
            // Éxito: notificación con alerta clara y banner visual
            alert(`✅ ¡Usuario '${data.username}' registrado exitosamente con rol '${data.rol}'!`);

            if (msgDiv) {
                msgDiv.className = "text-xs bg-emerald-50 text-emerald-800 border border-emerald-200 font-semibold block p-2 rounded-lg";
                msgDiv.textContent = `✅ Usuario '${data.username}' registrado exitosamente (${data.rol}).`;
            }

            const form = document.getElementById("nuevoUsuarioForm");
            if (form) form.reset();
            actualizarInfoSesionUsuariosModal();
            await cargarUsuariosModal();

            setTimeout(() => {
                if (msgDiv) msgDiv.className = "text-xs hidden font-medium p-2 rounded-lg";
            }, 5000);
        } else {
            let errorMsg = "Error al crear usuario";
            if (data && data.detail) {
                if (Array.isArray(data.detail)) {
                    errorMsg = data.detail.map(d => d.msg || JSON.stringify(d)).join(", ");
                } else {
                    errorMsg = data.detail;
                }
            }
            alert(`❌ No se pudo crear el usuario:\n${errorMsg}`);

            if (msgDiv) {
                msgDiv.className = "text-xs bg-rose-50 text-rose-800 border border-rose-200 font-semibold block p-2 rounded-lg";
                msgDiv.textContent = `❌ ${errorMsg}`;
            }
        }
    } catch (err) {
        console.error("Error al registrar usuario:", err);
        alert("❌ Error de comunicación con el servidor. Verifica que el backend esté activo.");
        if (msgDiv) {
            msgDiv.className = "text-xs bg-rose-50 text-rose-800 border border-rose-200 font-semibold block p-2 rounded-lg";
            msgDiv.textContent = "❌ Error de comunicación con el servidor.";
        }
    } finally {
        if (btnSubmit) {
            btnSubmit.disabled = false;
            btnSubmit.innerHTML = origBtnHtml;
        }
    }
}

async function eliminarUsuario(idUsuario, username) {
    if (!confirm(`¿Eliminar definitivamente al usuario '${username}'?`)) return;
    const token = getToken();
    try {
        const res = await fetch(`/api/admin/usuarios/${idUsuario}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${token}` }
        });
        const data = await res.json();
        if (res.ok) {
            alert(`✅ Usuario '${username}' eliminado correctamente.`);
            await cargarUsuariosModal();
        } else {
            alert(data.detail || "Error al eliminar usuario");
        }
    } catch (e) {
        alert("Error de conexión");
    }
}


// --- CAMBIO DE CONTRASEÑA ---

function openCambiarPasswordModal(esPrimerLogin = false) {
    const modal = document.getElementById("cambiarPasswordModal");
    const titulo = document.getElementById("cambiarPasswordTitulo");
    const subtitulo = document.getElementById("cambiarPasswordSubtitulo");
    const avisoPrimer = document.getElementById("avisoPrimerLogin");
    const btnCancelar = document.getElementById("btnCancelarCambiarPassword");
    const btnCerrar = document.getElementById("btnCerrarCambiarPassword");

    if (esPrimerLogin) {
        titulo.textContent = "Cambio de Contraseña Obligatorio";
        subtitulo.textContent = "Debes establecer una nueva contraseña antes de continuar";
        avisoPrimer.classList.remove("hidden");
        // En primer login no se puede cerrar el modal sin cambiar la contraseña
        btnCancelar.classList.add("hidden");
        btnCerrar.classList.add("hidden");
    } else {
        titulo.textContent = "Cambiar Contraseña";
        subtitulo.textContent = "Actualiza tu contraseña de acceso";
        avisoPrimer.classList.add("hidden");
        btnCancelar.classList.remove("hidden");
        btnCerrar.classList.remove("hidden");
    }

    document.getElementById("cambiarPasswordForm").reset();
    const msgDiv = document.getElementById("cpMsgDiv");
    if (msgDiv) msgDiv.className = "text-xs hidden font-medium p-2 rounded-lg";

    modal.classList.remove("hidden");
}

function closeCambiarPasswordModal() {
    // Solo se puede cerrar si NOT primer login
    if (currentUserProfile && currentUserProfile.must_change_password) {
        alert("⚠️ Debes cambiar tu contraseña antes de continuar.");
        return;
    }
    document.getElementById("cambiarPasswordModal").classList.add("hidden");
}

async function handleCambiarPassword(e) {
    e.preventDefault();
    const token = getToken();
    if (!token) { alert("Sesión expirada. Inicia sesión nuevamente."); return; }

    const actual = document.getElementById("cpPasswordActual").value;
    const nueva = document.getElementById("cpPasswordNueva").value.trim();
    const confirmar = document.getElementById("cpPasswordConfirm").value.trim();
    const msgDiv = document.getElementById("cpMsgDiv");
    const btnGuardar = document.getElementById("btnGuardarPassword");

    if (!actual || !nueva || !confirmar) {
        alert("Por favor completa todos los campos.");
        return;
    }
    if (nueva.length < 4) {
        alert("La nueva contraseña debe tener al menos 4 caracteres.");
        return;
    }
    if (nueva !== confirmar) {
        alert("❌ La nueva contraseña y la confirmación no coinciden.");
        return;
    }

    const origHtml = btnGuardar.innerHTML;
    btnGuardar.disabled = true;
    btnGuardar.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Guardando...`;
    if (msgDiv) msgDiv.className = "text-xs hidden font-medium p-2 rounded-lg";

    try {
        const res = await fetch("/api/auth/cambiar-password", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ password_actual: actual, password_nueva: nueva })
        });
        const data = await res.json();

        if (res.ok) {
            if (msgDiv) {
                msgDiv.className = "text-xs bg-emerald-50 text-emerald-800 border border-emerald-200 font-semibold block p-2 rounded-lg";
                msgDiv.textContent = "✅ Contraseña actualizada exitosamente.";
            }
            // Actualizar perfil local y cerrar modal
            if (currentUserProfile) currentUserProfile.must_change_password = false;
            setTimeout(() => {
                document.getElementById("cambiarPasswordModal").classList.add("hidden");
                alert("✅ Contraseña cambiada y actualizada exitosamente.");
            }, 600);
        } else {
            const errorMsg = data.detail || "Error al cambiar la contraseña";
            alert(`❌ ${errorMsg}`);
            if (msgDiv) {
                msgDiv.className = "text-xs bg-rose-50 text-rose-800 border border-rose-200 font-semibold block p-2 rounded-lg";
                msgDiv.textContent = `❌ ${errorMsg}`;
            }
        }
    } catch (err) {
        alert("❌ Error de conexión con el servidor.");
    } finally {
        btnGuardar.disabled = false;
        btnGuardar.innerHTML = origHtml;
    }
}


// --- WHATSAPP SEMANAL (Todos los cuidadores de la semana) ---

async function ejecutarEnvioWhatsAppSemanal() {
    const btn = document.getElementById("btnWhatsAppSemanal");
    const token = getToken();
    if (!token) { alert("Debes iniciar sesión para enviar notificaciones."); return; }

    if (!confirm("¿Enviar WhatsApp a TODOS los cuidadores de la semana completa?\n\nCada cuidador recibirá un mensaje consolidado con todos sus turnos y actividades de la semana.")) return;

    const origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Enviando a toda la semana...`;

    try {
        const res = await fetch("/api/admin/notificaciones/enviar-semana", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ fecha_base: formatDateIso(fechaActual) })
        });
        const data = await res.json();

        if (res.ok) {
            let resumen = `✅ WhatsApp semanal procesado\n\n📅 Semana: ${data.semana_inicio} al ${data.semana_fin}\n👥 Cuidadores en turno: ${data.total_cuidadores || 0}\n🕒 Turnos totales: ${data.total_asignaciones || 0}\n✉️ Mensajes enviados: ${data.enviados}\n❌ Errores: ${data.errores}\n`;
            if (data.detalles && data.detalles.length > 0) {
                resumen += "\nDetalle por cuidador/a:\n";
                data.detalles.forEach(d => {
                    resumen += `• ${d.cuidador} (${d.total_turnos} turnos): ${d.estado}${d.detalle_error ? ` (${d.detalle_error})` : ''}\n`;
                });
            } else if (data.total_asignaciones === 0) {
                resumen += "\nNo hay turnos asignados para esta semana.";
            }
            alert(resumen);
            await cargarCuadrante();
        } else {
            const err = data.detail || "Error al enviar notificaciones semanales";
            alert(`❌ ${err}`);
        }
    } catch (err) {
        alert("❌ Error de conexión al enviar WhatsApp semanal.");
    } finally {
        btn.disabled = false;
        btn.innerHTML = origHtml;
    }
}


// --- NOTIFICACIONES POR CORREO ELECTRÓNICO (RESEND HTTP API) ---

function openNotificacionEmailModal() {
    const inputFecha = document.getElementById("notifEmailFecha");
    if (inputFecha) inputFecha.value = formatDateIso(fechaActual || new Date());
    const resDiv = document.getElementById("notifEmailResultados");
    if (resDiv) resDiv.classList.add("hidden");
    document.getElementById("notificacionEmailModal").classList.remove("hidden");
}

function closeNotificacionEmailModal() {
    document.getElementById("notificacionEmailModal").classList.add("hidden");
}

function ejecutarEnvioCorreoDiario() {
    openNotificacionEmailModal();
}

async function ejecutarEnvioCorreoDiarioDesdeModal() {
    const token = getToken();
    if (!token) { alert("Debes iniciar sesión para enviar notificaciones."); return; }

    const inputFecha = document.getElementById("notifEmailFecha");
    const fecha = inputFecha ? inputFecha.value : formatDateIso(fechaActual);
    if (!fecha) {
        alert("Por favor selecciona una fecha.");
        return;
    }

    const btn = document.getElementById("btnDispararEmail");
    const resDiv = document.getElementById("notifEmailResultados");
    const listaDet = document.getElementById("resEmailDetallesLista");

    const origHtml = btn ? btn.innerHTML : "";
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Enviando...`;
    }

    try {
        const res = await fetch("/api/admin/notificaciones/enviar-email-dia", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ fecha })
        });
        const data = await res.json();

        if (res.ok) {
            document.getElementById("resEmailTotal").textContent = data.total_cuidadores;
            document.getElementById("resEmailEnviados").textContent = data.enviados;
            document.getElementById("resEmailOmitidos").textContent = data.omitidos;
            document.getElementById("resEmailErrores").textContent = data.errores;

            if (!data.detalles || data.detalles.length === 0) {
                listaDet.innerHTML = `<p class="text-xs text-slate-500 py-3 text-center">No se encontraron asignaciones de cuidadores para el día seleccionado (${fecha}).</p>`;
            } else {
                listaDet.innerHTML = data.detalles.map(d => {
                    let colorEstado = 'text-slate-600 bg-slate-100 border-slate-200';
                    let iconEstado = 'fa-regular fa-clock';
                    if (d.estado === 'ENVIADO') {
                        colorEstado = 'text-emerald-700 bg-emerald-50 border-emerald-200';
                        iconEstado = 'fa-solid fa-check';
                    } else if (d.estado === 'OMITIDO') {
                        colorEstado = 'text-amber-700 bg-amber-50 border-amber-200';
                        iconEstado = 'fa-solid fa-triangle-exclamation';
                    } else if (d.estado === 'ERROR') {
                        colorEstado = 'text-rose-700 bg-rose-50 border-rose-200';
                        iconEstado = 'fa-solid fa-circle-xmark';
                    }

                    return `
                        <div class="p-2.5 rounded-xl border border-slate-200 bg-white space-y-1 text-xs">
                            <div class="flex items-center justify-between font-bold">
                                <span>${d.cuidador}</span>
                                <span class="px-2 py-0.5 rounded text-[10px] font-semibold border flex items-center gap-1 ${colorEstado}">
                                    <i class="${iconEstado}"></i> ${d.estado}
                                </span>
                            </div>
                            <div class="text-[11px] text-slate-500 font-mono">
                                <i class="fa-solid fa-envelope text-sky-600 mr-1"></i>${d.mail || 'Sin correo registrado'}
                            </div>
                            ${d.detalle ? `<div class="text-[10px] text-slate-600 bg-slate-50 p-1.5 rounded border border-slate-100">${d.detalle}</div>` : ''}
                        </div>
                    `;
                }).join("");
            }

            resDiv.classList.remove("hidden");
        } else {
            alert(`❌ Error al enviar correos: ${data.detail || 'Error desconocido'}`);
        }
    } catch (err) {
        alert("❌ Error de conexión al enviar correos diarios.");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}

async function ejecutarEnvioCorreoSemanal() {
    const btn = document.getElementById("btnCorreoSemanal");
    const token = getToken();
    if (!token) { alert("Debes iniciar sesión para enviar notificaciones."); return; }

    const fechaIso = formatDateIso(fechaActual);
    if (!confirm(`¿Enviar Correo Semanal con la planificación a todos los cuidadores de la semana?\n\nSe enviará a todos los cuidadores con turnos asignados que tengan correo configurado.`)) return;

    const origHtml = btn ? btn.innerHTML : "";
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Enviando semana...`;
    }

    try {
        const res = await fetch("/api/admin/notificaciones/enviar-email-semana", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ fecha_base: fechaIso })
        });
        const data = await res.json();

        if (res.ok) {
            let resumen = `📧 Planificación semanal por correo procesada\n\n📅 Periodo: ${data.periodo}\n👥 Cuidadores con turnos: ${data.total_cuidadores}\n✉️ Correos enviados: ${data.enviados}\n⚠️ Omitidos (sin correo): ${data.omitidos}\n❌ Errores: ${data.errores}\n`;
            if (data.detalles && data.detalles.length > 0) {
                resumen += "\nDetalle por cuidador/a:\n";
                data.detalles.forEach(d => {
                    resumen += `• ${d.cuidador} [${d.mail || 'Sin correo'}]: ${d.estado}${d.detalle ? ` (${d.detalle})` : ''}\n`;
                });
            } else if (data.total_cuidadores === 0) {
                resumen += "\nNo hay turnos asignados para esta semana.";
            }
            alert(resumen);
        } else {
            alert(`❌ Error al enviar correos semanales: ${data.detail || 'Error desconocido'}`);
        }
    } catch (err) {
        alert("❌ Error de conexión al enviar correos semanales.");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }
}


// ============================================================================
// --- MÓDULO DE GENERACIÓN DE IMAGEN DEL HORARIO SEMANAL (ESTILO AFICHE CANVA) ---
// ============================================================================

const PALETAS_DIAS = [
    { bg: "#E8DEF2", border: "#D5C4E5", fg: "#74528C", name: "LUNES" },
    { bg: "#DCE7DB", border: "#C2D7C0", fg: "#537950", name: "MARTES" },
    { bg: "#FCE2D6", border: "#F6C1AC", fg: "#B66447", name: "MIÉRCOLES" },
    { bg: "#D5E6E9", border: "#B5D6DC", fg: "#3F7580", name: "JUEVES" },
    { bg: "#F8DFE4", border: "#F0BCC6", fg: "#A44C60", name: "VIERNES" },
    { bg: "#F5E8D4", border: "#E6CFAA", fg: "#9D7033", name: "SÁBADO" },
    { bg: "#DEE8DD", border: "#C4D6C2", fg: "#5B7B59", name: "DOMINGO" }
];

/**
 * Abre el modal para visualizar y descargar la imagen del horario semanal
 */
async function abrirModalGenerarImagen() {
    const modal = document.getElementById("modalGenerarImagen");
    const spinner = document.getElementById("imagenCargandoSpinner");
    const preview = document.getElementById("previewImagenHorario");
    const textarea = document.getElementById("textoNotasPostIt");

    if (!modal) return;
    modal.classList.remove("hidden");
    spinner.classList.remove("hidden");
    preview.classList.add("hidden");

    // Asegurar que existan datos del cuadrante
    if (!cuadranteData) {
        try {
            await cargarCuadrante();
        } catch (e) {
            console.error("Error al cargar cuadrante para imagen:", e);
        }
    }

    // Asegurar que existan actividades de la semana
    if (!listaActividadesCache || listaActividadesCache.length === 0) {
        try {
            const fechaIso = formatDateIso(fechaActual);
            const res = await fetch(`/api/public/actividades-semana?fecha_base=${fechaIso}`);
            if (res.ok) {
                listaActividadesCache = await res.json();
            }
        } catch (e) {
            console.warn("No se pudieron cargar actividades para el post-it:", e);
        }
    }

    // Cargar notas predeterminadas de la semana
    if (textarea) {
        textarea.value = construirTextoNotasSemanales();
    }

    // Generar imagen
    await regenerarImagenConNotas();
}

/**
 * Cierra el modal de imagen
 */
function cerrarModalGenerarImagen() {
    const modal = document.getElementById("modalGenerarImagen");
    if (modal) modal.classList.add("hidden");
}

/**
 * Construye el texto en formato bullet points para el post-it amarillo
 */
function construirTextoNotasSemanales() {
    if (!listaActividadesCache || listaActividadesCache.length === 0) {
        return "• Sin actividades médicas programadas para esta semana.";
    }

    return listaActividadesCache.map(act => {
        const fechaObj = new Date(act.fecha + "T00:00:00");
        const diaNum = String(fechaObj.getDate()).padStart(2, "0");
        const mesNum = String(fechaObj.getMonth() + 1).padStart(2, "0");
        const horaStr = act.hora ? act.hora.slice(0, 5) + "hrs" : "";
        let medicoStr = "";
        if (act.medico_asignado) {
            const nomMed = (act.medico_asignado.nombre + (act.medico_asignado.apellido ? " " + act.medico_asignado.apellido : "")).trim();
            medicoStr = ` (A cargo: ${nomMed})`;
        }
        let linea = `• ${diaNum}/${mesNum} ${act.titulo}`;
        if (horaStr) linea += ` ${horaStr}`;
        if (act.descripcion) linea += ` - ${act.descripcion}`;
        if (medicoStr) linea += medicoStr;
        return linea;
    }).join("\n");
}

/**
 * Dibuja o redibuja el poster en el canvas y actualiza la vista previa
 */
async function regenerarImagenConNotas() {
    const spinner = document.getElementById("imagenCargandoSpinner");
    const preview = document.getElementById("previewImagenHorario");
    const textarea = document.getElementById("textoNotasPostIt");

    if (spinner) spinner.classList.remove("hidden");
    if (preview) preview.classList.add("hidden");

    // Esperar a que las fuentes web estén listas para evitar fallos tipográficos
    try {
        if (document.fonts) {
            await document.fonts.ready;
        }
    } catch (e) {
        console.warn("document.fonts.ready:", e);
    }

    const notasTexto = textarea ? textarea.value : construirTextoNotasSemanales();
    canvasPosterGlobal = dibujarPosterSemanal(cuadranteData, notasTexto);

    if (canvasPosterGlobal) {
        const dataUrl = canvasPosterGlobal.toDataURL("image/png");
        if (preview) {
            preview.src = dataUrl;
            preview.classList.remove("hidden");
        }
    }

    if (spinner) spinner.classList.add("hidden");
}

/**
 * Función principal de dibujo en Canvas HTML5 (1600 x 1056 px)
 */
function dibujarPosterSemanal(data, notasTexto) {
    const width = 1600;
    const height = 1056;

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");

    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";

    // 1. Fondo suave papel cálido
    ctx.fillStyle = "#FCFAF8";
    ctx.fillRect(0, 0, width, height);

    // 2. Acuarela y ramitas decorativas en esquina inferior derecha
    dibujarAcuarelaYBotánicaFondo(ctx, width, height);

    // 3. Encabezado principal: "✦ CALENDARIO SEMANAL ✦"
    const goldColor = "#C5A059";
    const darkNavy = "#1E293B";
    const scriptGold = "#C59B6C";

    // Líneas doradas laterales del encabezado
    ctx.strokeStyle = goldColor;
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    ctx.moveTo(110, 48);
    ctx.lineTo(365, 48);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(1235, 48);
    ctx.lineTo(1490, 48);
    ctx.stroke();

    // Estrellas / Diamantes ✦
    dibujarEstrellaDiamante(ctx, 390, 48, 12, goldColor);
    dibujarEstrellaDiamante(ctx, 1210, 48, 12, goldColor);

    // Título en fuente Serif
    ctx.save();
    ctx.fillStyle = darkNavy;
    ctx.font = "700 42px 'Cinzel', 'Playfair Display', 'Georgia', serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    if (ctx.letterSpacing !== undefined) {
        ctx.letterSpacing = "6px";
    }
    ctx.fillText("CALENDARIO SEMANAL", 800, 48);
    ctx.restore();

    // Subtítulo en caligrafía script elegante: "Planificación de Personal"
    ctx.save();
    ctx.fillStyle = scriptGold;
    ctx.font = "italic 600 38px 'Dancing Script', 'Caveat', cursive";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("Planificación de Personal", 800, 98);
    ctx.restore();

    // 4. Mapeo de bloques desde cuadranteData
    const bloques = (data && data.bloques) || [];
    const bloqueAM = bloques.find(b => (b.codigo_bloque || "").toUpperCase() === "AM" || (b.nombre_bloque || "").toUpperCase().includes("AM"));
    const bloquesPM = bloques.filter(b => {
        const cod = (b.codigo_bloque || "").toUpperCase();
        const nom = (b.nombre_bloque || "").toUpperCase();
        return (cod.startsWith("PM") || nom.includes("PM")) && cod !== "AM" && cod !== "N";
    });
    const bloqueN = bloques.find(b => (b.codigo_bloque || "").toUpperCase() === "N" || (b.nombre_bloque || "").toUpperCase().includes("NOCTURN"));

    const diasList = (data && data.dias) || [];
    const matriz = (data && data.matriz) || {};

    const leftMargin = 38;
    const colGap = 16;
    const colWidth = 204;

    // 5. Dibujar las 7 Columnas de Lunes a Domingo
    for (let i = 0; i < 7; i++) {
        const colX = leftMargin + i * (colWidth + colGap);
        const colCx = colX + colWidth / 2;
        const paleta = PALETAS_DIAS[i % PALETAS_DIAS.length];
        const diaInfo = diasList[i] || {};

        // Fecha DD/MM
        let fechaStr = "";
        let diaNombre = paleta.name;
        if (diaInfo.fecha) {
            const p = diaInfo.fecha.split("-");
            if (p.length === 3) {
                fechaStr = `${parseInt(p[2], 10)}/${parseInt(p[1], 10)}`;
            }
        }
        if (diaInfo.nombre) {
            diaNombre = diaInfo.nombre.toUpperCase();
        }

        // --- ENCABEZADO DE LA COLUMNA ---
        // Óvalo pastel a la izquierda con ramita botánica
        const ovalCx = colX + 44;
        const ovalCy = 196;
        ctx.save();
        ctx.fillStyle = paleta.bg;
        ctx.beginPath();
        ctx.ellipse(ovalCx, ovalCy, 27, 43, 0, 0, Math.PI * 2);
        ctx.fill();
        dibujarRamitaBotanica(ctx, ovalCx, ovalCy, paleta.fg);
        ctx.restore();

        // Nombre del día a la derecha del óvalo
        const dayRx = colX + 130;
        ctx.save();
        ctx.fillStyle = "#334155";
        ctx.font = "800 15px 'Inter', -apple-system, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(diaNombre, dayRx, 166);

        // Línea divisoria dorada sutil
        ctx.strokeStyle = "#D8C29D";
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(dayRx - 28, 186);
        ctx.lineTo(dayRx + 28, 186);
        ctx.stroke();

        // Círculo / Medallón con la fecha
        const dateCy = 230;
        ctx.fillStyle = "#FFFFFF";
        ctx.strokeStyle = "#D8C29D";
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        ctx.ellipse(dayRx, dateCy, 26, 24, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = "#0F172A";
        ctx.font = "700 17px 'Inter', -apple-system, sans-serif";
        ctx.fillText(fechaStr || `${19 + i}/10`, dayRx, dateCy + 1);
        ctx.restore();

        // --- RECOPILACIÓN DE ASIGNACIONES POR TURNO ---
        const fIso = diaInfo.fecha;

        // Turno AM
        let asigsAM = [];
        if (bloqueAM && fIso && matriz[bloqueAM.id_bloque] && matriz[bloqueAM.id_bloque][fIso]) {
            asigsAM = matriz[bloqueAM.id_bloque][fIso];
        }

        // Turnos PM
        let pmShifts = [];
        let hasReunionPM = false;
        bloquesPM.forEach(b => {
            if (fIso && matriz[b.id_bloque] && matriz[b.id_bloque][fIso]) {
                const as = matriz[b.id_bloque][fIso];
                if (as.length > 0) {
                    const timeTxt = as[0].horario_texto ? as[0].horario_texto.replace(" - ", "/ ") : "PM";
                    const namesTxt = as.map(a => a.cuidador_nombre).join(" + ");
                    const tieneReunion = as.some(a => a.reunion_familiar);
                    if (tieneReunion) hasReunionPM = true;
                    pmShifts.push({ time: timeTxt, names: namesTxt, reunion_familiar: tieneReunion });
                }
            }
        });

        // Turno N (Nocturno)
        let asigsN = [];
        if (bloqueN && fIso && matriz[bloqueN.id_bloque] && matriz[bloqueN.id_bloque][fIso]) {
            asigsN = matriz[bloqueN.id_bloque][fIso];
        }

        // --- TARJETA 1: AM (Y: 295, Alto: 152) ---
        const amY = 295;
        const amH = 152;
        const hasReunionAM = asigsAM.some(a => a.reunion_familiar);
        dibujarCajaTarjeta(ctx, colX, amY, colWidth, amH);
        dibujarPastillaTurno(ctx, colCx, amY + 22, "AM", paleta.bg, paleta.fg);
        dibujarIconoSol(ctx, colX + 34, amY + 86, "#D09B59");

        ctx.save();
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        const amCenterContentX = colX + 116;

        if (asigsAM.length > 0) {
            const hText = asigsAM[0].horario_texto || "10:00 - 14:30";
            ctx.fillStyle = "#0F172A";
            ctx.font = "700 13px 'Inter', sans-serif";
            const hY = hasReunionAM ? (amY + 60) : (amY + 70);
            ctx.fillText(hText, amCenterContentX, hY);

            const nText = asigsAM.map(a => a.cuidador_nombre).join(" + ");
            ctx.font = "700 15px 'Inter', sans-serif";
            const nYPos = hasReunionAM ? (amY + 84) : (amY + 95);
            dibujarTextoConSalto(ctx, nText, amCenterContentX, nYPos, colWidth - 75, 17);

            if (hasReunionAM) {
                dibujarBadgeReunionFamiliar(ctx, colCx, amY + 126);
            }
        } else {
            ctx.fillStyle = "#94A3B8";
            ctx.font = "600 18px 'Inter', sans-serif";
            ctx.fillText("—", amCenterContentX, amY + 86);
            if (hasReunionAM) {
                dibujarBadgeReunionFamiliar(ctx, colCx, amY + 126);
            }
        }
        ctx.restore();

        // --- TARJETA 2: PM (Y: 462, Alto: 156) ---
        const pmY = 462;
        const pmH = 156;
        dibujarCajaTarjeta(ctx, colX, pmY, colWidth, pmH);
        dibujarPastillaTurno(ctx, colCx, pmY + 22, "PM", paleta.bg, paleta.fg);
        dibujarIconoAtardecer(ctx, colX + 34, pmY + 90, "#D09B59");

        ctx.save();
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        const pmCenterContentX = colX + 116;

        if (pmShifts.length === 1) {
            const s = pmShifts[0];
            ctx.fillStyle = "#0F172A";
            ctx.font = "700 13px 'Inter', sans-serif";
            const hY = s.reunion_familiar ? (pmY + 60) : (pmY + 70);
            ctx.fillText(s.time, pmCenterContentX, hY);

            ctx.font = "700 15px 'Inter', sans-serif";
            const nYPos = s.reunion_familiar ? (pmY + 84) : (pmY + 96);
            dibujarTextoConSalto(ctx, s.names, pmCenterContentX, nYPos, colWidth - 75, 17);

            if (s.reunion_familiar) {
                dibujarBadgeReunionFamiliar(ctx, colCx, pmY + 128);
            }
        } else if (pmShifts.length >= 2) {
            // Múltiples turnos de tarde (PM1 y PM2)
            ctx.fillStyle = "#0F172A";
            ctx.font = "700 11.5px 'Inter', sans-serif";
            ctx.fillText(pmShifts[0].time, pmCenterContentX, pmY + 48);
            ctx.font = "700 13.5px 'Inter', sans-serif";
            ctx.fillText(pmShifts[0].names, pmCenterContentX, pmY + 65);

            ctx.font = "700 11.5px 'Inter', sans-serif";
            ctx.fillText(pmShifts[1].time, pmCenterContentX, pmY + 88);
            ctx.font = "700 13.5px 'Inter', sans-serif";
            ctx.fillText(pmShifts[1].names, pmCenterContentX, pmY + 105);

            if (hasReunionPM) {
                dibujarBadgeReunionFamiliar(ctx, colCx, pmY + 134);
            }
        } else {
            ctx.fillStyle = "#94A3B8";
            ctx.font = "600 18px 'Inter', sans-serif";
            ctx.fillText("—", pmCenterContentX, pmY + 90);
            if (hasReunionPM) {
                dibujarBadgeReunionFamiliar(ctx, colCx, pmY + 128);
            }
        }
        ctx.restore();

        // --- TARJETA 3: N / Nocturno (Y: 632, Alto: 122) ---
        const nY = 632;
        const nH = 122;
        const hasReunionN = asigsN.some(a => a.reunion_familiar);
        dibujarCajaTarjeta(ctx, colX, nY, colWidth, nH);
        dibujarPastillaTurno(ctx, colCx, nY + 22, "N", "#1E293B", "#FFFFFF");
        dibujarIconoLuna(ctx, colX + 34, nY + 70, "#1E293B");

        ctx.save();
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        const nCenterContentX = colX + 116;

        if (asigsN.length > 0) {
            const hText = asigsN[0].horario_texto ? asigsN[0].horario_texto.replace(" - ", "/") : "21:00/10:00";
            ctx.fillStyle = "#0F172A";
            ctx.font = "700 12.5px 'Inter', sans-serif";
            const hY = hasReunionN ? (nY + 44) : (nY + 56);
            ctx.fillText(hText, nCenterContentX, hY);

            const nText = asigsN.map(a => a.cuidador_nombre).join(" + ");
            ctx.font = "700 15px 'Inter', sans-serif";
            const nYPos = hasReunionN ? (nY + 66) : (nY + 84);
            dibujarTextoConSalto(ctx, nText, nCenterContentX, nYPos, colWidth - 75, 17);

            if (hasReunionN) {
                dibujarBadgeReunionFamiliar(ctx, colCx, nY + 102);
            }
        } else {
            ctx.fillStyle = "#94A3B8";
            ctx.font = "600 18px 'Inter', sans-serif";
            ctx.fillText("—", nCenterContentX, nY + 70);
            if (hasReunionN) {
                dibujarBadgeReunionFamiliar(ctx, colCx, nY + 102);
            }
        }
        ctx.restore();
    }

    // 6. SECCIÓN INFERIOR
    // 6.1 Emblema circular en la esquina inferior izquierda
    dibujarEmblemaCuidados(ctx, 136, 915);

    // 6.2 Post-It Amarillo con Actividades Médicas
    dibujarPostItActividades(ctx, 360, 785, 590, 235, notasTexto);

    return canvas;
}

/**
 * Dibuja un diamante / estrella de 4 puntas ✦
 */
function dibujarEstrellaDiamante(ctx, cx, cy, size, color) {
    ctx.save();
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(cx, cy - size);
    ctx.quadraticCurveTo(cx, cy, cx + size * 0.7, cy);
    ctx.quadraticCurveTo(cx, cy, cx, cy + size);
    ctx.quadraticCurveTo(cx, cy, cx - size * 0.7, cy);
    ctx.quadraticCurveTo(cx, cy, cx, cy - size);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
}

/**
 * Dibuja una ramita botánica con hojas estilizadas orgánicas
 */
function dibujarRamitaBotanica(ctx, cx, cy, color) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 2.0;
    ctx.lineCap = "round";

    // Tallo central curvado
    ctx.beginPath();
    ctx.moveTo(cx, cy + 28);
    ctx.quadraticCurveTo(cx - 1, cy, cx + 2, cy - 26);
    ctx.stroke();

    // Hojas laterales
    const hojas = [
        { ox: -13, oy: -17, rot: -0.65, rx: 9.5, ry: 4.5 },
        { ox: 13, oy: -10, rot: 0.65, rx: 9.5, ry: 4.5 },
        { ox: -14, oy: -2, rot: -0.55, rx: 10, ry: 5 },
        { ox: 14, oy: 6, rot: 0.55, rx: 10, ry: 5 },
        { ox: -13, oy: 13, rot: -0.45, rx: 9, ry: 4.5 },
        { ox: 13, oy: 20, rot: 0.45, rx: 8.5, ry: 4 },
        { ox: 2, oy: -28, rot: 0.05, rx: 7.5, ry: 3.5 }
    ];

    hojas.forEach(h => {
        ctx.save();
        ctx.translate(cx + h.ox * 0.85, cy + h.oy);
        ctx.rotate(h.rot);
        ctx.beginPath();
        ctx.ellipse(0, 0, h.rx, h.ry, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    });

    ctx.restore();
}

/**
 * Dibuja el marco de la tarjeta de turno
 */
function dibujarCajaTarjeta(ctx, x, y, w, h) {
    ctx.save();
    ctx.fillStyle = "#FFFFFF";
    ctx.strokeStyle = "rgba(203, 213, 225, 0.75)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    if (ctx.roundRect) {
        ctx.roundRect(x, y, w, h, 16);
    } else {
        ctx.rect(x, y, w, h);
    }
    ctx.fill();
    ctx.stroke();
    ctx.restore();
}

/**
 * Dibuja la píldora / etiqueta del turno ("AM", "PM", "N")
 */
function dibujarPastillaTurno(ctx, cx, cy, texto, bg, fg) {
    ctx.save();
    const w = 68;
    const h = 24;
    ctx.fillStyle = bg;
    ctx.beginPath();
    if (ctx.roundRect) {
        ctx.roundRect(cx - w / 2, cy - h / 2, w, h, 12);
    } else {
        ctx.rect(cx - w / 2, cy - h / 2, w, h);
    }
    ctx.fill();

    ctx.fillStyle = fg;
    ctx.font = "800 12.5px 'Inter', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(texto, cx, cy);
    ctx.restore();
}

/**
 * Dibuja la píldora / etiqueta de REUNION FAMILIAR en mayúsculas en la tarjeta
 */
function dibujarBadgeReunionFamiliar(ctx, cx, cy) {
    ctx.save();
    const w = 152;
    const h = 20;
    ctx.fillStyle = "#F59E0B"; // Amber 500
    ctx.strokeStyle = "#D97706"; // Amber 600
    ctx.lineWidth = 1;
    ctx.beginPath();
    if (ctx.roundRect) {
        ctx.roundRect(cx - w / 2, cy - h / 2, w, h, 6);
    } else {
        ctx.rect(cx - w / 2, cy - h / 2, w, h);
    }
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#FFFFFF";
    ctx.font = "800 10.5px 'Inter', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("REUNION FAMILIAR", cx, cy + 0.5);
    ctx.restore();
}

/**
 * Dibuja el icono de sol matutino
 */
function dibujarIconoSol(ctx, cx, cy, color) {
    ctx.save();
    ctx.fillStyle = color;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    ctx.arc(cx, cy, 7.5, 0, Math.PI * 2);
    ctx.fill();

    for (let a = 0; a < 360; a += 45) {
        const rad = (a * Math.PI) / 180;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(rad) * 11, cy + Math.sin(rad) * 11);
        ctx.lineTo(cx + Math.cos(rad) * 16, cy + Math.sin(rad) * 16);
        ctx.stroke();
    }
    ctx.restore();
}

/**
 * Dibuja el icono de atardecer / puesta de sol
 */
function dibujarIconoAtardecer(ctx, cx, cy, color) {
    ctx.save();
    ctx.fillStyle = color;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.8;

    // Línea de horizonte
    ctx.beginPath();
    ctx.moveTo(cx - 15, cy + 3);
    ctx.lineTo(cx + 15, cy + 3);
    ctx.stroke();

    // Semicírculo sol hundiéndose
    ctx.beginPath();
    ctx.arc(cx, cy + 3, 9, Math.PI, 0);
    ctx.fill();

    // Rayos superiores
    [-55, -25, 0, 25, 55].forEach(deg => {
        const rad = ((deg - 90) * Math.PI) / 180;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(rad) * 12, cy + 3 + Math.sin(rad) * 12);
        ctx.lineTo(cx + Math.cos(rad) * 16, cy + 3 + Math.sin(rad) * 16);
        ctx.stroke();
    });

    // Ondulación de agua debajo
    ctx.beginPath();
    ctx.moveTo(cx - 10, cy + 7);
    ctx.lineTo(cx + 10, cy + 7);
    ctx.stroke();

    ctx.restore();
}

/**
 * Dibuja el icono de luna nocturna en medallón marino
 */
function dibujarIconoLuna(ctx, cx, cy, navyColor) {
    ctx.save();
    // Medallón marino
    ctx.fillStyle = navyColor;
    ctx.beginPath();
    ctx.arc(cx, cy, 16, 0, Math.PI * 2);
    ctx.fill();

    // Media luna blanca
    ctx.fillStyle = "#FFFFFF";
    ctx.beginPath();
    ctx.arc(cx - 1, cy, 9, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = navyColor;
    ctx.beginPath();
    ctx.arc(cx + 3.5, cy - 2, 7.5, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
}

/**
 * Dibuja texto con salto de línea automático si supera el ancho máximo
 */
function dibujarTextoConSalto(ctx, texto, cx, cy, maxW, lineH) {
    const palabras = (texto || "").split(" ");
    let lineas = [];
    let curLine = "";

    for (const p of palabras) {
        const test = curLine ? curLine + " " + p : p;
        if (ctx.measureText(test).width > maxW && curLine) {
            lineas.push(curLine);
            curLine = p;
        } else {
            curLine = test;
        }
    }
    if (curLine) lineas.push(curLine);

    if (lineas.length === 1) {
        ctx.fillText(lineas[0], cx, cy);
    } else if (lineas.length === 2) {
        ctx.fillText(lineas[0], cx, cy - lineH / 2);
        ctx.fillText(lineas[1], cx, cy + lineH / 2);
    } else {
        // Reducir temporalmente tamaño si son más líneas
        ctx.save();
        ctx.font = "700 13px 'Inter', sans-serif";
        let startY = cy - ((lineas.length - 1) * (lineH - 4)) / 2;
        lineas.forEach(l => {
            ctx.fillText(l, cx, startY);
            startY += (lineH - 4);
        });
        ctx.restore();
    }
}

/**
 * Dibuja el emblema circular en la esquina inferior izquierda
 */
function dibujarEmblemaCuidados(ctx, cx, cy) {
    ctx.save();
    // Círculo azul marino principal
    ctx.fillStyle = "#15243B";
    ctx.beginPath();
    ctx.arc(cx, cy, 54, 0, Math.PI * 2);
    ctx.fill();

    // Anillos dorados concéntricos
    ctx.strokeStyle = "#D4AF37";
    ctx.lineWidth = 2.0;
    ctx.beginPath();
    ctx.arc(cx, cy, 48, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = "rgba(212, 175, 55, 0.4)";
    ctx.lineWidth = 1.0;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.arc(cx, cy, 43, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);

    // Ramitas de laurel doradas en los costados
    ctx.fillStyle = "#C5A059";
    for (let i = -3; i <= 3; i++) {
        const angleL = Math.PI - 0.25 - (i * 0.24);
        const lx = cx + Math.cos(angleL) * 58;
        const ly = cy + Math.sin(angleL) * 58;
        ctx.save();
        ctx.translate(lx, ly);
        ctx.rotate(angleL + 0.5);
        ctx.beginPath();
        ctx.ellipse(0, 0, 5, 2.5, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }

    // 3 Figuras humanas estilizadas en dorado (cuidador / familia)
    ctx.fillStyle = "#D4AF37";
    // Cabezas
    ctx.beginPath();
    ctx.arc(cx - 15, cy - 9, 5.5, 0, Math.PI * 2);
    ctx.arc(cx, cy - 13, 7, 0, Math.PI * 2);
    ctx.arc(cx + 15, cy - 9, 5.5, 0, Math.PI * 2);
    ctx.fill();

    // Cuerpos
    ctx.beginPath();
    ctx.arc(cx - 15, cy + 10, 10, Math.PI, 0);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cx, cy + 9, 13, Math.PI, 0);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cx + 15, cy + 10, 10, Math.PI, 0);
    ctx.fill();

    // Medallón pequeño inferior con corazón blanco
    ctx.fillStyle = "#C5A059";
    ctx.strokeStyle = "#FFFFFF";
    ctx.lineWidth = 2.0;
    ctx.beginPath();
    ctx.arc(cx, cy + 42, 12, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#FFFFFF";
    const hx = cx, hy = cy + 41;
    ctx.beginPath();
    ctx.moveTo(hx, hy + 4);
    ctx.bezierCurveTo(hx - 5, hy, hx - 5, hy - 4, hx, hy - 2);
    ctx.bezierCurveTo(hx + 5, hy - 4, hx + 5, hy, hx, hy + 4);
    ctx.fill();

    ctx.restore();
}

/**
 * Dibuja el post-it amarillo con notas y cinta adhesiva en las esquinas
 */
function dibujarPostItActividades(ctx, x, y, width, height, notasTexto) {
    ctx.save();
    ctx.translate(x + width / 2, y + height / 2);
    ctx.rotate(-1.2 * Math.PI / 180);

    // Sombra suave realista
    ctx.shadowColor = "rgba(0, 0, 0, 0.12)";
    ctx.shadowBlur = 14;
    ctx.shadowOffsetX = 3;
    ctx.shadowOffsetY = 6;

    // Cuerpo del post-it con degradado amarillo suave
    const grad = ctx.createLinearGradient(-width / 2, -height / 2, width / 2, height / 2);
    grad.addColorStop(0, "#FFF9CE");
    grad.addColorStop(1, "#FFEFA2");
    ctx.fillStyle = grad;
    ctx.beginPath();
    if (ctx.roundRect) {
        ctx.roundRect(-width / 2, -height / 2, width, height, 6);
    } else {
        ctx.rect(-width / 2, -height / 2, width, height);
    }
    ctx.fill();

    ctx.shadowColor = "transparent";

    // Cinta adhesiva / Washi tape esquina superior izquierda
    ctx.save();
    ctx.translate(-width / 2 + 28, -height / 2 + 8);
    ctx.rotate(-32 * Math.PI / 180);
    ctx.fillStyle = "rgba(245, 222, 145, 0.82)";
    ctx.fillRect(-38, -13, 76, 26);
    ctx.strokeStyle = "rgba(220, 195, 120, 0.5)";
    ctx.lineWidth = 1;
    ctx.strokeRect(-38, -13, 76, 26);
    ctx.restore();

    // Cinta adhesiva / Washi tape esquina inferior derecha
    ctx.save();
    ctx.translate(width / 2 - 24, height / 2 - 8);
    ctx.rotate(-38 * Math.PI / 180);
    ctx.fillStyle = "rgba(245, 222, 145, 0.82)";
    ctx.fillRect(-38, -13, 76, 26);
    ctx.strokeStyle = "rgba(220, 195, 120, 0.5)";
    ctx.lineWidth = 1;
    ctx.strokeRect(-38, -13, 76, 26);
    ctx.restore();

    // Texto de actividades / notas dentro del post-it
    ctx.fillStyle = "#1A202C";
    ctx.font = "600 15px 'Inter', -apple-system, sans-serif";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";

    const paddingX = -width / 2 + 35;
    const maxTextW = width - 70;
    let currentY = -height / 2 + 24;

    const lineas = (notasTexto || "").split("\n");
    for (const rawLine of lineas) {
        const clean = rawLine.trim();
        if (!clean) {
            currentY += 6;
            continue;
        }

        const palabras = clean.split(" ");
        let cur = "";
        for (const w of palabras) {
            const test = cur ? cur + " " + w : w;
            if (ctx.measureText(test).width > maxTextW && cur) {
                ctx.fillText(cur, paddingX, currentY);
                currentY += 23;
                cur = "   " + w;
            } else {
                cur = test;
            }
        }
        if (cur) {
            ctx.fillText(cur, paddingX, currentY);
            currentY += 25;
        }
    }

    ctx.restore();
}

/**
 * Dibuja la acuarela y ramitas botánicas doradas en la esquina inferior derecha
 */
function dibujarAcuarelaYBotánicaFondo(ctx, width, height) {
    ctx.save();
    // Lavados de acuarela celeste suave y arena
    const grad1 = ctx.createRadialGradient(width - 150, height - 100, 20, width - 150, height - 100, 240);
    grad1.addColorStop(0, "rgba(202, 225, 237, 0.55)");
    grad1.addColorStop(0.6, "rgba(224, 238, 245, 0.25)");
    grad1.addColorStop(1, "rgba(252, 250, 247, 0)");
    ctx.fillStyle = grad1;
    ctx.fillRect(width - 390, height - 340, 390, 340);

    const grad2 = ctx.createRadialGradient(width - 200, height - 70, 10, width - 200, height - 70, 190);
    grad2.addColorStop(0, "rgba(242, 232, 215, 0.5)");
    grad2.addColorStop(0.7, "rgba(247, 241, 230, 0.2)");
    grad2.addColorStop(1, "rgba(252, 250, 247, 0)");
    ctx.fillStyle = grad2;
    ctx.fillRect(width - 390, height - 260, 390, 260);

    // Tallo floral botánico dorado ascendente
    ctx.strokeStyle = "#C5A059";
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    ctx.moveTo(width - 20, height);
    ctx.quadraticCurveTo(width - 110, height - 120, width - 145, height - 225);
    ctx.stroke();

    // Hojas doradas translúcidas
    const branchLeaves = [
        { x: width - 50, y: height - 50, rx: 19, ry: 7.5, rot: -0.8 },
        { x: width - 85, y: height - 90, rx: 21, ry: 8.5, rot: 0.6 },
        { x: width - 105, y: height - 140, rx: 22, ry: 9, rot: -0.7 },
        { x: width - 128, y: height - 180, rx: 20, ry: 8, rot: 0.5 },
        { x: width - 145, y: height - 225, rx: 18, ry: 7, rot: -0.2 }
    ];
    ctx.fillStyle = "rgba(212, 175, 55, 0.18)";
    branchLeaves.forEach(bl => {
        ctx.save();
        ctx.translate(bl.x, bl.y);
        ctx.rotate(bl.rot);
        ctx.beginPath();
        ctx.ellipse(0, 0, bl.rx, bl.ry, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.restore();
    });

    // Línea de puntos dorada sutil
    ctx.setLineDash([4, 6]);
    ctx.strokeStyle = "rgba(212, 175, 55, 0.6)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(width - 270, height - 50, 160, Math.PI * 1.5, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.restore();
}

/**
 * Descarga la imagen generada en formato PNG o JPEG
 */
function descargarImagenGenerada(formato = "png") {
    if (!canvasPosterGlobal) {
        alert("Primero debes generar la imagen.");
        return;
    }

    const fmt = formato.toLowerCase() === "jpeg" || formato.toLowerCase() === "jpg" ? "jpeg" : "png";
    const mime = fmt === "jpeg" ? "image/jpeg" : "image/png";
    const calidad = fmt === "jpeg" ? 0.95 : undefined;

    const dataUrl = canvasPosterGlobal.toDataURL(mime, calidad);

    let nombreArchivo = "horario_semanal";
    if (cuadranteData && cuadranteData.inicio_semana && cuadranteData.fin_semana) {
        nombreArchivo = `horario_${cuadranteData.inicio_semana}_al_${cuadranteData.fin_semana}`;
    }

    const a = document.createElement("a");
    a.href = dataUrl;
    a.download = `${nombreArchivo}.${fmt}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

/**
 * Copia la imagen directamente al portapapeles para pegar en WhatsApp Web o chat
 */
async function copiarImagenAlPortapapeles() {
    if (!canvasPosterGlobal) {
        alert("Primero debes generar la imagen.");
        return;
    }

    const btnTexto = document.getElementById("textoBtnCopiar");
    const orig = btnTexto ? btnTexto.textContent : "Copiar Imagen";

    try {
        canvasPosterGlobal.toBlob(async (blob) => {
            if (!blob) {
                alert("No se pudo procesar la imagen.");
                return;
            }
            try {
                await navigator.clipboard.write([
                    new ClipboardItem({ "image/png": blob })
                ]);
                if (btnTexto) btnTexto.textContent = "¡Copiada con éxito!";
                setTimeout(() => {
                    if (btnTexto) btnTexto.textContent = orig;
                }, 2500);
            } catch (err) {
                console.warn("Clipboard write failed, fallback:", err);
                alert("Tu navegador no permitió copiar directamente al portapapeles. Usa el botón 'Descargar PNG' o 'Descargar JPG'.");
            }
        }, "image/png");
    } catch (e) {
        console.error("Error al copiar imagen:", e);
        alert("No se pudo copiar la imagen al portapapeles. Puedes descargarla directamente con el botón Descargar.");
    }
}


// ==============================================================================
// --- GESTIÓN DE MEDICAMENTOS (FRONTEND) ---
// ==============================================================================

let listaTratamientosCache = [];
let horasInicialesSeleccionadas = [];
let fechasExtrasSeleccionadas = [];
let tabMedicamentosActivo = 'nuevo';

/**
 * Carga la lista completa de tratamientos y los renderiza en el dashboard principal.
 */
async function cargarMedicamentos() {
    const cont = document.getElementById("contenedorMedicamentos");
    if (!cont) return;

    try {
        const res = await fetch("/api/medicamentos/");
        if (!res.ok) throw new Error("Error obteniendo tratamientos");
        const tratamientos = await res.json();
        listaTratamientosCache = Array.isArray(tratamientos) ? tratamientos : [];

        // Actualizar select de filtro por médico en el dashboard
        actualizarSelectFiltroMedicosDashboard();

        // Renderizar en el contenedor principal
        renderizarMedicamentosEnDashboard(listaTratamientosCache);
    } catch (err) {
        console.error("Error cargando medicamentos:", err);
        cont.innerHTML = `
            <div class="col-span-full text-center py-8 text-rose-500 bg-rose-50/50 rounded-xl border border-dashed border-rose-200">
                <p class="text-xs font-medium">Error al cargar tratamientos de medicamentos.</p>
            </div>
        `;
    }
}

function actualizarSelectFiltroMedicosDashboard() {
    const select = document.getElementById("filtroMedicoMedicamentos");
    if (!select) return;

    const valActual = select.value;
    select.innerHTML = '<option value="">Todos los médicos</option>';

    listaMedicosCache.forEach(m => {
        const opt = document.createElement("option");
        opt.value = m.id_medico;
        const nombreMed = `${m.nombre} ${m.apellido || ''}`.trim();
        opt.textContent = `${nombreMed} (${m.especialidad})`;
        select.appendChild(opt);
    });

    select.value = valActual;
}

function filtrarMedicamentosDashboard() {
    const select = document.getElementById("filtroMedicoMedicamentos");
    const idMed = select ? select.value : "";
    if (!idMed) {
        renderizarMedicamentosEnDashboard(listaTratamientosCache);
    } else {
        const filtrados = listaTratamientosCache.filter(t => String(t.personal_medico_id) === String(idMed));
        renderizarMedicamentosEnDashboard(filtrados);
    }
}

function renderizarMedicamentosEnDashboard(tratamientos) {
    const cont = document.getElementById("contenedorMedicamentos");
    if (!cont) return;
    const esAdmin = !!getToken();

    if (!tratamientos || tratamientos.length === 0) {
        cont.innerHTML = `
            <div class="col-span-full text-center py-8 text-slate-400 bg-slate-50/70 rounded-xl border border-dashed border-slate-200">
                <i class="fa-solid fa-pills text-2xl mb-2 text-slate-300"></i>
                <p class="text-xs font-medium">No hay tratamientos de medicamentos registrados.</p>
                ${esAdmin ? `
                    <button onclick="openMedicamentosModal()" class="mt-2.5 px-3 py-1.5 text-xs font-semibold bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 rounded-lg transition-colors inline-flex items-center gap-1.5">
                        <i class="fa-solid fa-plus text-xs"></i>
                        <span>Registrar Primer Tratamiento</span>
                    </button>
                ` : ''}
            </div>
        `;
        return;
    }

    cont.innerHTML = tratamientos.map(t => {
        const nombreMed = t.personal_medico 
            ? `${t.personal_medico.nombre} ${t.personal_medico.apellido || ''}`.trim()
            : "Médico asignado";
        const espMed = t.personal_medico ? t.personal_medico.especialidad : "";

        // Ordenar horarios
        const horariosOrdenados = (t.horarios || []).slice().sort((a, b) => {
            if (a.dia === b.dia) return a.hora.localeCompare(b.hora);
            return a.dia.localeCompare(b.dia);
        });

        // Agrupar horarios por día
        const horariosPorDia = {};
        horariosOrdenados.forEach(h => {
            if (!horariosPorDia[h.dia]) horariosPorDia[h.dia] = [];
            horariosPorDia[h.dia].push(h.hora.slice(0, 5));
        });

        const totalTomas = horariosOrdenados.length;
        const diasTotales = Object.keys(horariosPorDia).length;

        // Renderizar resumen de días/horas
        const previewsDiasHtml = Object.entries(horariosPorDia).slice(0, 3).map(([dia, horas]) => {
            const fechaObj = new Date(dia + "T00:00:00");
            const diasSem = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
            const sem = diasSem[fechaObj.getDay()];
            const num = fechaObj.getDate();
            return `
                <div class="flex items-center justify-between text-[11px] bg-slate-50 px-2 py-1 rounded-md border border-slate-100">
                    <span class="font-semibold text-slate-700">${sem} ${num}:</span>
                    <span class="text-rose-600 font-medium">${horas.join(', ')} hrs</span>
                </div>
            `;
        }).join("");

        const masDias = diasTotales > 3 ? `<span class="text-[10px] text-slate-400 block text-center">+ ${diasTotales - 3} días más...</span>` : '';

        return `
            <div class="p-4 rounded-xl border border-slate-200 bg-white hover:border-rose-300 hover:shadow-md transition-all space-y-3 flex flex-col justify-between">
                <div class="space-y-2">
                    <div class="flex items-start justify-between gap-2">
                        <div class="flex items-center space-x-2">
                            <span class="w-7 h-7 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center text-xs">
                                <i class="fa-solid fa-capsules"></i>
                            </span>
                            <div>
                                <h4 class="font-bold text-sm text-slate-900 leading-snug">${t.nombre_medicamento}</h4>
                                <span class="text-[10px] text-slate-400">Inicio: ${t.dia_inicial}</span>
                            </div>
                        </div>
                        ${esAdmin ? `
                            <div class="flex items-center space-x-1">
                                <button onclick="openClonarHorariosModal(${JSON.stringify(t).replace(/"/g, '&quot;')})" title="Clonar / Extender días" class="p-1 text-slate-400 hover:text-rose-600 transition-colors">
                                    <i class="fa-regular fa-copy text-xs"></i>
                                </button>
                                <button onclick="eliminarTratamientoUI(${t.id})" title="Eliminar tratamiento" class="p-1 text-slate-400 hover:text-rose-600 transition-colors">
                                    <i class="fa-regular fa-trash-can text-xs"></i>
                                </button>
                            </div>
                        ` : ''}
                    </div>

                    <!-- Pauta y horas -->
                    <div class="space-y-1.5 pt-1">
                        <div class="flex items-center justify-between text-[11px]">
                            <span class="text-slate-500 font-medium">Tomas programadas:</span>
                            <span class="px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 font-bold text-[10px] border border-rose-100">${totalTomas} tomas (${diasTotales} días)</span>
                        </div>
                        <div class="space-y-1">
                            ${previewsDiasHtml}
                            ${masDias}
                        </div>
                    </div>
                </div>

                <!-- Footer médico -->
                <div class="pt-2 border-t border-slate-100 flex items-center justify-between text-xs">
                    <div class="flex items-center space-x-1.5 text-teal-700 font-medium truncate">
                        <i class="fa-solid fa-user-doctor text-[11px]"></i>
                        <span class="truncate" title="${nombreMed} (${espMed})">${nombreMed}</span>
                    </div>
                    ${esAdmin ? `
                        <button onclick="openClonarHorariosModal(${JSON.stringify(t).replace(/"/g, '&quot;')})" class="text-[11px] font-semibold text-rose-600 hover:text-rose-700">
                            + Extender
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    }).join("");
}

/**
 * Abre el modal de Medicamentos y prepara los selects de médico y fechas.
 */
function openMedicamentosModal() {
    poblarSelectsMedicosMedicamentos();

    // Fecha inicial por defecto
    const inputDia = document.getElementById("medTratDiaInicial");
    if (inputDia) {
        inputDia.value = formatDateIso(fechaActual);
    }

    // Limpiar horas y tags
    horasInicialesSeleccionadas = [];
    fechasExtrasSeleccionadas = [];
    renderizarHorasInicialesTags();
    renderizarFechasExtrasTags();

    // Resetear formulario
    const form = document.getElementById("nuevoTratamientoForm");
    if (form) form.reset();
    if (inputDia) inputDia.value = formatDateIso(fechaActual);

    // Cargar pautas en pestaña 2
    consultarPautaMedicoUI();

    // Cambiar a pestaña 1
    cambiarTabMedicamentos('nuevo');

    const modal = document.getElementById("medicamentosModal");
    if (modal) modal.classList.remove("hidden");
}

function closeMedicamentosModal() {
    const modal = document.getElementById("medicamentosModal");
    if (modal) modal.classList.add("hidden");
}

function poblarSelectsMedicosMedicamentos() {
    const select1 = document.getElementById("medTratPersonalMedico");
    const select2 = document.getElementById("medConsultaMedico");

    if (select1) {
        select1.innerHTML = '<option value="">Sin médico asignado (Opcional)...</option>';
        listaMedicosCache.filter(m => m.activo).forEach(m => {
            const opt = document.createElement("option");
            opt.value = m.id_medico;
            const nom = `${m.nombre} ${m.apellido || ''}`.trim();
            opt.textContent = `${nom} - ${m.especialidad}`;
            select1.appendChild(opt);
        });
    }

    if (select2) {
        select2.innerHTML = '<option value="">Todos los profesionales</option>';
        listaMedicosCache.forEach(m => {
            const opt = document.createElement("option");
            opt.value = m.id_medico;
            const nom = `${m.nombre} ${m.apellido || ''}`.trim();
            opt.textContent = `${nom} - ${m.especialidad}`;
            select2.appendChild(opt);
        });
    }
}

function cambiarTabMedicamentos(tab) {
    tabMedicamentosActivo = tab;
    const btnNuevo = document.getElementById("tabBtnNuevoTratamiento");
    const btnPautas = document.getElementById("tabBtnPautasTratamiento");
    const contNuevo = document.getElementById("tabContenidoNuevoTratamiento");
    const contPautas = document.getElementById("tabContenidoPautasTratamiento");

    if (!btnNuevo || !btnPautas || !contNuevo || !contPautas) return;

    if (tab === 'nuevo') {
        btnNuevo.className = "py-2 px-4 border-b-2 border-rose-600 text-rose-600 transition-colors flex items-center gap-1.5";
        btnPautas.className = "py-2 px-4 border-b-2 border-transparent text-slate-500 hover:text-slate-700 transition-colors flex items-center gap-1.5";
        contNuevo.classList.remove("hidden");
        contPautas.classList.add("hidden");
    } else {
        btnPautas.className = "py-2 px-4 border-b-2 border-rose-600 text-rose-600 transition-colors flex items-center gap-1.5";
        btnNuevo.className = "py-2 px-4 border-b-2 border-transparent text-slate-500 hover:text-slate-700 transition-colors flex items-center gap-1.5";
        contPautas.classList.remove("hidden");
        contNuevo.classList.add("hidden");
        consultarPautaMedicoUI();
    }
}

function agregarPresetHora(horaStr) {
    if (!horasInicialesSeleccionadas.includes(horaStr)) {
        horasInicialesSeleccionadas.push(horaStr);
        horasInicialesSeleccionadas.sort();
        renderizarHorasInicialesTags();
    }
}

function agregarHoraInicialDesdeInput() {
    const input = document.getElementById("medTratHoraInput");
    if (!input || !input.value) return;
    const horaVal = input.value.slice(0, 5);
    if (!horasInicialesSeleccionadas.includes(horaVal)) {
        horasInicialesSeleccionadas.push(horaVal);
        horasInicialesSeleccionadas.sort();
        renderizarHorasInicialesTags();
    }
    input.value = "";
}

function eliminarHoraInicial(idx) {
    horasInicialesSeleccionadas.splice(idx, 1);
    renderizarHorasInicialesTags();
}

function renderizarHorasInicialesTags() {
    const cont = document.getElementById("medTratHorasTags");
    if (!cont) return;

    if (horasInicialesSeleccionadas.length === 0) {
        cont.innerHTML = `<span class="text-[11px] text-slate-400 italic">No has agregado horarios aún.</span>`;
        return;
    }

    cont.innerHTML = horasInicialesSeleccionadas.map((h, idx) => `
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-rose-50 border border-rose-200 text-rose-700 text-xs font-bold">
            <i class="fa-regular fa-clock text-[10px]"></i>
            <span>${h}</span>
            <button type="button" onclick="eliminarHoraInicial(${idx})" class="text-rose-400 hover:text-rose-700 ml-0.5 text-xs font-bold">&times;</button>
        </span>
    `).join("");
}

function agregarFechaExtraDesdeInput() {
    const input = document.getElementById("medTratFechaExtraInput");
    if (!input || !input.value) return;
    const fechaVal = input.value;
    if (!fechasExtrasSeleccionadas.includes(fechaVal)) {
        fechasExtrasSeleccionadas.push(fechaVal);
        fechasExtrasSeleccionadas.sort();
        renderizarFechasExtrasTags();
    }
    input.value = "";
}

function eliminarFechaExtra(idx) {
    fechasExtrasSeleccionadas.splice(idx, 1);
    renderizarFechasExtrasTags();
}

function renderizarFechasExtrasTags() {
    const cont = document.getElementById("medTratFechasExtrasTags");
    if (!cont) return;

    cont.innerHTML = fechasExtrasSeleccionadas.map((f, idx) => `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-semibold">
            <span>${f}</span>
            <button type="button" onclick="eliminarFechaExtra(${idx})" class="text-slate-400 hover:text-slate-700">&times;</button>
        </span>
    `).join("");
}

async function handleCrearTratamiento(e) {
    e.preventDefault();
    const token = getToken();

    const personalMedicoId = document.getElementById("medTratPersonalMedico").value;
    const nombreMed = document.getElementById("medTratNombre").value.trim();
    const diaInicial = document.getElementById("medTratDiaInicial").value;
    const duracionDias = document.getElementById("medTratDuracionDias").value;


    if (!nombreMed) {
        alert("Por favor ingresa el nombre del medicamento.");
        return;
    }
    if (!diaInicial) {
        alert("Por favor selecciona el día inicial.");
        return;
    }
    if (horasInicialesSeleccionadas.length === 0) {
        alert("Por favor agrega al menos un horario inicial de toma (ej: 08:00).");
        return;
    }

    const payload = {
        personal_medico_id: personalMedicoId ? parseInt(personalMedicoId) : null,
        nombre_medicamento: nombreMed,
        dia_inicial: diaInicial,
        horarios_iniciales: horasInicialesSeleccionadas.map(h => h.length === 5 ? `${h}:00` : h)
    };

    if (duracionDias && parseInt(duracionDias) > 1) {
        payload.duracion_dias = parseInt(duracionDias);
    }
    if (fechasExtrasSeleccionadas.length > 0) {
        payload.fechas_adicionales = fechasExtrasSeleccionadas;
    }

    const btnSubmit = document.getElementById("btnSubmitTratamiento");
    if (btnSubmit) btnSubmit.disabled = true;

    try {
        const headers = { "Content-Type": "application/json" };
        if (token) headers["Authorization"] = `Bearer ${token}`;

        const res = await fetch("/api/medicamentos/", {
            method: "POST",
            headers: headers,
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            const data = await res.json();
            alert(`¡Tratamiento de ${data.nombre_medicamento} registrado exitosamente con ${data.horarios ? data.horarios.length : 0} tomas programadas!`);
            
            // Limpiar y recargar
            horasInicialesSeleccionadas = [];
            fechasExtrasSeleccionadas = [];
            renderizarHorasInicialesTags();
            renderizarFechasExtrasTags();
            document.getElementById("nuevoTratamientoForm").reset();

            await cargarMedicamentos();
            cambiarTabMedicamentos('pautas');
        } else {
            const err = await res.json();
            alert(err.detail || "Error al registrar tratamiento de medicamento");
        }
    } catch (err) {
        console.error("Error al registrar tratamiento:", err);
        alert("Error de conexión al guardar el tratamiento.");
    } finally {
        if (btnSubmit) btnSubmit.disabled = false;
    }
}

/**
 * Consulta la pauta de medicamentos asignada a un médico o general filtrada por fecha.
 */
async function consultarPautaMedicoUI() {
    const cont = document.getElementById("listaTratamientosModal");
    if (!cont) return;

    const selectMed = document.getElementById("medConsultaMedico");
    const inputFecha = document.getElementById("medConsultaFecha");

    const medId = selectMed ? selectMed.value : "";
    const fechaVal = inputFecha ? inputFecha.value : "";

    let url = "/api/medicamentos/";
    if (medId) {
        url = `/api/medicamentos/${medId}`;
        if (fechaVal) url += `?fecha=${fechaVal}`;
    } else {
        if (fechaVal) url += `?fecha=${fechaVal}`;
    }

    try {
        cont.innerHTML = `<p class="text-xs text-slate-400 py-4 text-center"><i class="fa-solid fa-spinner fa-spin mr-1"></i> Consultando pautas...</p>`;
        const res = await fetch(url);
        if (!res.ok) throw new Error("Error consultando pautas");
        const tratamientos = await res.json();

        if (!tratamientos || tratamientos.length === 0) {
            cont.innerHTML = `
                <div class="text-center py-6 text-slate-400 bg-white rounded-xl border border-dashed border-slate-200">
                    <p class="text-xs">No se encontraron medicamentos para el criterio seleccionado.</p>
                </div>
            `;
            return;
        }

        cont.innerHTML = tratamientos.map(t => {
            const nomMed = t.personal_medico ? `${t.personal_medico.nombre} ${t.personal_medico.apellido || ''}`.trim() : "Médico";
            const horariosList = (t.horarios || []).map(h => {
                const fStr = h.dia;
                const hStr = h.hora.slice(0, 5);
                return `
                    <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-50 border border-rose-200 text-rose-800 text-[11px] font-semibold">
                        <span>${fStr} ${hStr}</span>
                        <button type="button" onclick="eliminarHorarioIndividualUI(${h.id})" title="Eliminar toma horaria" class="text-rose-400 hover:text-rose-700 ml-0.5">&times;</button>
                    </span>
                `;
            }).join("");

            return `
                <div class="p-3.5 rounded-xl border border-slate-200 bg-white space-y-2">
                    <div class="flex items-start justify-between">
                        <div>
                            <div class="font-bold text-xs text-slate-900">${t.nombre_medicamento}</div>
                            <div class="text-[11px] text-teal-700 font-medium">${nomMed} &bull; Inicio: ${t.dia_inicial}</div>
                        </div>
                        <div class="flex items-center gap-1.5">
                            <button onclick="openClonarHorariosModal(${JSON.stringify(t).replace(/"/g, '&quot;')})" title="Extender días" class="px-2 py-1 text-[10px] font-semibold bg-rose-50 hover:bg-rose-100 text-rose-700 rounded-md transition-colors">
                                + Extender
                            </button>
                            <button onclick="eliminarTratamientoUI(${t.id})" title="Eliminar tratamiento completo" class="p-1 text-slate-400 hover:text-rose-600">
                                <i class="fa-regular fa-trash-can text-xs"></i>
                            </button>
                        </div>
                    </div>

                    <div class="pt-1.5 border-t border-slate-100">
                        <span class="text-[10px] text-slate-500 font-medium block mb-1">Horarios y Días Activos:</span>
                        <div class="flex flex-wrap gap-1">
                            ${horariosList || '<span class="text-[10px] text-slate-400 italic">Sin horarios en esta fecha.</span>'}
                        </div>
                    </div>
                </div>
            `;
        }).join("");
    } catch (err) {
        console.error("Error consultando pautas:", err);
        cont.innerHTML = `<p class="text-xs text-rose-500 py-3 text-center">Error al consultar pautas.</p>`;
    }
}

function limpiarFiltroFechaConsulta() {
    const input = document.getElementById("medConsultaFecha");
    if (input) input.value = "";
    consultarPautaMedicoUI();
}

/**
 * Modal para clonar o extender días en un tratamiento existente.
 */
function openClonarHorariosModal(tratamiento) {
    if (!tratamiento) return;
    document.getElementById("clonarTratamientoId").value = tratamiento.id;
    document.getElementById("clonarNombreMedicamento").textContent = tratamiento.nombre_medicamento;
    document.getElementById("clonarDiasNum").value = 7;
    document.getElementById("clonarFechaPuntual").value = "";

    const modal = document.getElementById("clonarHorariosModal");
    if (modal) modal.classList.remove("hidden");
}

function closeClonarHorariosModal() {
    const modal = document.getElementById("clonarHorariosModal");
    if (modal) modal.classList.add("hidden");
}

async function handleClonarHorarios(e) {
    e.preventDefault();
    const token = getToken();
    const tratId = document.getElementById("clonarTratamientoId").value;
    const diasNum = document.getElementById("clonarDiasNum").value;
    const fechaPuntual = document.getElementById("clonarFechaPuntual").value;

    const payload = {};
    if (diasNum && parseInt(diasNum) > 0) {
        payload.dias_a_clonar = parseInt(diasNum);
    }
    if (fechaPuntual) {
        payload.fechas = [fechaPuntual];
    }

    try {
        const headers = { "Content-Type": "application/json" };
        if (token) headers["Authorization"] = `Bearer ${token}`;

        const res = await fetch(`/api/medicamentos/${tratId}/horarios`, {
            method: "POST",
            headers: headers,
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            closeClonarHorariosModal();
            alert("¡Horarios clonados y extendidos exitosamente!");
            await cargarMedicamentos();
            consultarPautaMedicoUI();
        } else {
            const err = await res.json();
            alert(err.detail || "Error al clonar horarios");
        }
    } catch (err) {
        alert("Error de conexión al clonar horarios");
    }
}

async function eliminarTratamientoUI(tratamientoId) {
    if (!confirm("¿Eliminar este tratamiento y todos sus horarios en cascada?")) return;
    const token = getToken();

    try {
        const headers = {};
        if (token) headers["Authorization"] = `Bearer ${token}`;

        const res = await fetch(`/api/medicamentos/${tratamientoId}`, {
            method: "DELETE",
            headers: headers
        });

        if (res.ok) {
            await cargarMedicamentos();
            consultarPautaMedicoUI();
        } else {
            const err = await res.json();
            alert(err.detail || "Error al eliminar tratamiento");
        }
    } catch (err) {
        alert("Error de conexión al eliminar tratamiento");
    }
}

async function eliminarHorarioIndividualUI(horarioId) {
    if (!confirm("¿Eliminar este horario puntual de toma?")) return;
    const token = getToken();

    try {
        const headers = {};
        if (token) headers["Authorization"] = `Bearer ${token}`;

        const res = await fetch(`/api/medicamentos/horarios/${horarioId}`, {
            method: "DELETE",
            headers: headers
        });

        if (res.ok) {
            await cargarMedicamentos();
            consultarPautaMedicoUI();
        } else {
            const err = await res.json();
            alert(err.detail || "Error al eliminar horario");
        }
    } catch (err) {
        alert("Error de conexión al eliminar horario");
    }
}


