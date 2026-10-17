import uvicorn

if __name__ == "__main__":
    print("Iniciando Sistema de Gestión de Turnos y Actividades Médicas...")
    print("URL Local: http://localhost:8000")
    print("Documentación Swagger API: http://localhost:8000/docs")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
