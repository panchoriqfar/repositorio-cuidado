/**
 * MedTurnos Pro - Frontend Logic
 * Gestión de Turnos de Cuidadores y Actividades Médicas
 */

let fechaActual = new Date();
let cuadranteData = null;
let listaCuidadoresCache = [];
let listaMedicosCache = [];
let listaBloquesCache = [];
let currentUserProfile = null;

// Inicialización
document.addEventListener("DOMContentLoaded", async () => {
    actualizarInputFechaPicker(fechaActual);
    await checkAuth();
    await cargarDatosIniciales();
    await cargarCuadrante();
    await cargarActividades();
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
        if (btnGestionUsuarios) {
            btnGestionUsuarios.classList.add("hidden");
            btnGestionUsuarios.classList.remove("inline-flex");
        }
        const barraWhatsappSemanal = document.getElementById("barraWhatsappSemanal");
        if (barraWhatsappSemanal) {
            barraWhatsappSemanal.classList.add("hidden");
            barraWhatsappSemanal.classList.remove("flex");
        }
        loginBtn.classList.remove("hidden");
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

            loginBtn.classList.add("hidden");

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
}

function irSemanaActual() {
    fechaActual = new Date();
    actualizarInputFechaPicker(fechaActual);
    cargarCuadrante();
    cargarActividades();
}

function seleccionarFecha(valorStr) {
    if (valorStr) {
        const partes = valorStr.split("-");
        fechaActual = new Date(partes[0], partes[1] - 1, partes[2]);
        cargarCuadrante();
        cargarActividades();
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
            .map(m => `<option value="${m.id_medico}">${m.nombre} ${m.apellido} (${m.especialidad})</option>`)
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
            tdBloque.className = "p-4 align-middle bg-slate-50/50 border-r border-slate-100 text-center sm:text-left";
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
                ? `${act.medico_asignado.nombre} ${act.medico_asignado.apellido} (${act.medico_asignado.especialidad})`
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
    autoSugerirBloque();
    limpiarCuidadoresAdicionales();
    document.getElementById("asignacionModal").classList.remove("hidden");
}

function closeAsignacionModal() {
    limpiarCuidadoresAdicionales();
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
        id_bloque
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
            <div class="flex items-center space-x-2">
                <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${c.activo ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}">
                    ${c.activo ? 'Activo' : 'Inactivo'}
                </span>
                ${c.activo ? (esSuper ? `
                    <button onclick="desactivarCuidador(${c.id_cuidador})" title="Desactivar cuidador (super_user)" class="text-xs text-rose-500 hover:text-rose-700 p-1 transition-colors">
                        <i class="fa-solid fa-user-xmark"></i>
                    </button>
                ` : `
                    <span title="Restricción: Solo super_user tiene permitido eliminar cuidadores" class="text-xs text-slate-300 p-1 cursor-not-allowed">
                        <i class="fa-solid fa-lock text-slate-400"></i>
                    </span>
                `) : ''}
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
                <div class="text-xs font-bold text-slate-900">${m.nombre} ${m.apellido}</div>
                <div class="text-[11px] text-teal-700">${m.especialidad} &bull; ${m.telefono_whatsapp}</div>
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
    const apellido = document.getElementById("medApellido").value.trim();
    const telefono_whatsapp = document.getElementById("medTelefono").value.trim();
    const especialidad = document.getElementById("medEspecialidad").value.trim();

    try {
        const res = await fetch("/api/admin/medicos", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ nombre, apellido, telefono_whatsapp, especialidad, activo: true })
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


// --- ACCIONES ADMIN: WHATSAPP ---
function openNotificacionModal() {
    const inputFecha = document.getElementById("notifFecha");
    if (inputFecha) inputFecha.value = formatDateIso(fechaActual || new Date());
    document.getElementById("notifResultados").classList.add("hidden");
    document.getElementById("notificacionModal").classList.remove("hidden");
}

function closeNotificacionModal() {
    document.getElementById("notificacionModal").classList.add("hidden");
}

async function ejecutarEnvioWhatsApp() {
    const token = getToken();
    const fecha = document.getElementById("notifFecha").value;
    const btn = document.getElementById("btnDispararWhatsApp");
    const resDiv = document.getElementById("notifResultados");
    const listaDet = document.getElementById("resDetallesLista");

    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Enviando...`;

    try {
        const res = await fetch("/api/admin/notificaciones/enviar-dia", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ fecha })
        });

        if (res.ok) {
            const data = await res.json();
            document.getElementById("resTotal").textContent = data.total_asignaciones;
            document.getElementById("resEnviados").textContent = data.enviados;
            document.getElementById("resErrores").textContent = data.errores;

            if (data.detalles.length === 0) {
                listaDet.innerHTML = `<p class="text-xs text-slate-500 py-2">No se encontraron asignaciones de cuidadores para la fecha seleccionada.</p>`;
            } else {
                listaDet.innerHTML = data.detalles.map(d => `
                    <div class="p-2.5 rounded-lg border border-slate-200 bg-white space-y-1">
                        <div class="flex items-center justify-between text-xs font-bold">
                            <span>${d.personal} (${d.telefono})</span>
                            <span class="${d.estado.includes('ENVIADO') ? 'text-emerald-600' : 'text-rose-600'}">
                                ${d.estado}
                            </span>
                        </div>
                        <div class="text-[11px] text-slate-600">Bloque: ${d.bloque} &bull; Horario: <strong>${d.horario}</strong></div>
                        ${d.detalle_error ? `<div class="text-[10px] text-amber-600">${d.detalle_error}</div>` : ''}
                    </div>
                `).join("");
            }

            resDiv.classList.remove("hidden");
            cargarCuadrante();
        } else {
            const err = await res.json();
            alert(err.detail || "Error al disparar notificaciones");
        }
    } catch (e) {
        alert("Error de conexión");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-paper-plane"></i> <span>Disparar Envío Ahora</span>`;
    }
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
