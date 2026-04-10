APP_NAME = "CineVerse"
APP_TAGLINE = "Reserva funciones, snacks y experiencias premium en las principales ciudades de Colombia."
INSTITUTIONAL_DOMAIN = "cinecol.com"
ALLOWED_USER_EMAIL_DOMAINS = {"gmail.com"}

DEFAULT_CITY_NAME = "Barranquilla"
DEFAULT_SEDE_NAME = "CineVerse Buenavista"

PROJECTION_FORMATS = ["2D", "3D", "IMAX", "VIP"]
PAYMENT_METHODS = ["tarjeta", "nequi", "bancolombia", "otro"]

CITY_SEED = [
    {
        "nombre": "Barranquilla",
        "sedes": ["CineVerse Buenavista", "CineVerse Portal del Rio"],
    },
    {
        "nombre": "Bogota",
        "sedes": ["CineVerse Andino", "CineVerse Gran Estacion"],
    },
    {
        "nombre": "Medellin",
        "sedes": ["CineVerse El Tesoro", "CineVerse Oviedo"],
    },
    {
        "nombre": "Cali",
        "sedes": ["CineVerse Chipichape"],
    },
    {
        "nombre": "Cartagena",
        "sedes": ["CineVerse Caribe Plaza"],
    },
    {
        "nombre": "Bucaramanga",
        "sedes": ["CineVerse Cacique"],
    },
    {
        "nombre": "Armenia",
        "sedes": ["CineVerse Portal del Quindio"],
    },
]

SNACK_COMBOS = [
    {
        "id": "combo_orbita",
        "name": "Combo Orbita",
        "description": "Crispetas medianas, gaseosa grande y chocolatina.",
        "price": 23000,
        "tag": "Top ventas",
    },
    {
        "id": "combo_duo",
        "name": "Combo Duo Estelar",
        "description": "Crispetas grandes, 2 bebidas y nachos para compartir.",
        "price": 36000,
        "tag": "Compartir",
    },
    {
        "id": "combo_kids",
        "name": "Combo Mini Nova",
        "description": "Crispetas pequenas, jugo y gomitas.",
        "price": 18000,
        "tag": "Kids",
    },
    {
        "id": "combo_midnight",
        "name": "Combo Midnight",
        "description": "Perro caliente, papas, bebida y refill de crispetas.",
        "price": 32000,
        "tag": "Maraton",
    },
]

MOVIE_SEED = [
    {
        "titulo": "Duna: Parte Dos",
        "descripcion": "Paul Atreides avanza sobre Arrakis mientras el desierto redefine el destino del imperio.",
        "duracion": 166,
        "genero": "Ciencia ficcion",
        "categoria": "Estreno",
        "clasificacion": "+13",
        "imagen_url": "/static/img/posters/duna-parte-dos.svg",
        "trailer_url": "",
        "funciones": [
            {"offset_days": 0, "time": "16:20:00", "city": "Barranquilla", "venue": "CineVerse Buenavista", "room": "Sala Atlas", "price": 24000, "format": "IMAX"},
            {"offset_days": 0, "time": "20:00:00", "city": "Bogota", "venue": "CineVerse Andino", "room": "Sala Atlas", "price": 25500, "format": "IMAX"},
            {"offset_days": 1, "time": "19:10:00", "city": "Medellin", "venue": "CineVerse El Tesoro", "room": "Sala Origen", "price": 22500, "format": "2D"},
        ],
    },
    {
        "titulo": "Intensa-Mente 2",
        "descripcion": "Nuevas emociones llegan al cuartel general de Riley justo cuando todo empieza a cambiar.",
        "duracion": 97,
        "genero": "Animacion",
        "categoria": "Familia",
        "clasificacion": "+7",
        "imagen_url": "/static/img/posters/intensa-mente-2.svg",
        "trailer_url": "",
        "funciones": [
            {"offset_days": 0, "time": "13:10:00", "city": "Barranquilla", "venue": "CineVerse Portal del Rio", "room": "Sala Prisma", "price": 17000, "format": "2D"},
            {"offset_days": 0, "time": "15:30:00", "city": "Barranquilla", "venue": "CineVerse Buenavista", "room": "Sala Prisma", "price": 17500, "format": "2D"},
            {"offset_days": 1, "time": "14:00:00", "city": "Bogota", "venue": "CineVerse Gran Estacion", "room": "Sala Rio", "price": 18500, "format": "3D"},
        ],
    },
    {
        "titulo": "Godzilla y Kong: El Nuevo Imperio",
        "descripcion": "Dos titanes se enfrentan a una amenaza escondida bajo la corteza del planeta.",
        "duracion": 115,
        "genero": "Accion",
        "categoria": "Tendencias",
        "clasificacion": "+13",
        "imagen_url": "/static/img/posters/godzilla-kong.svg",
        "trailer_url": "",
        "funciones": [
            {"offset_days": 0, "time": "18:40:00", "city": "Barranquilla", "venue": "CineVerse Buenavista", "room": "Sala Titan", "price": 21500, "format": "3D"},
            {"offset_days": 0, "time": "21:10:00", "city": "Cartagena", "venue": "CineVerse Caribe Plaza", "room": "Sala Titan", "price": 22500, "format": "3D"},
            {"offset_days": 1, "time": "19:30:00", "city": "Cali", "venue": "CineVerse Chipichape", "room": "Sala Pacifico", "price": 22000, "format": "IMAX"},
        ],
    },
    {
        "titulo": "El Especialista",
        "descripcion": "Un doble de accion regresa al set para salvar una pelicula y desenredar una conspiracion.",
        "duracion": 126,
        "genero": "Accion",
        "categoria": "Accion",
        "clasificacion": "+13",
        "imagen_url": "/static/img/posters/el-especialista.svg",
        "trailer_url": "",
        "funciones": [
            {"offset_days": 0, "time": "17:45:00", "city": "Barranquilla", "venue": "CineVerse Buenavista", "room": "Sala Nova", "price": 19500, "format": "VIP"},
            {"offset_days": 1, "time": "20:20:00", "city": "Bogota", "venue": "CineVerse Andino", "room": "Sala Nova", "price": 21000, "format": "VIP"},
            {"offset_days": 0, "time": "19:50:00", "city": "Medellin", "venue": "CineVerse Oviedo", "room": "Sala Capital", "price": 21000, "format": "2D"},
        ],
    },
    {
        "titulo": "Kung Fu Panda 4",
        "descripcion": "Po debe entrenar a un nuevo guardian mientras una hechicera amenaza el Valle de la Paz.",
        "duracion": 94,
        "genero": "Comedia",
        "categoria": "Familia",
        "clasificacion": "+7",
        "imagen_url": "/static/img/posters/kung-fu-panda-4.svg",
        "trailer_url": "",
        "funciones": [
            {"offset_days": 0, "time": "12:20:00", "city": "Barranquilla", "venue": "CineVerse Buenavista", "room": "Sala Bambu", "price": 16500, "format": "2D"},
            {"offset_days": 0, "time": "14:30:00", "city": "Armenia", "venue": "CineVerse Portal del Quindio", "room": "Sala Bambu", "price": 17000, "format": "2D"},
            {"offset_days": 1, "time": "16:10:00", "city": "Bogota", "venue": "CineVerse Gran Estacion", "room": "Sala Cafe", "price": 17500, "format": "3D"},
        ],
    },
    {
        "titulo": "Robot Salvaje",
        "descripcion": "Una robot naufraga en una isla y descubre que la naturaleza tambien puede convertirse en hogar.",
        "duracion": 102,
        "genero": "Aventura",
        "categoria": "Estreno",
        "clasificacion": "+7",
        "imagen_url": "/static/img/posters/robot-salvaje.svg",
        "trailer_url": "",
        "funciones": [
            {"offset_days": 0, "time": "15:50:00", "city": "Barranquilla", "venue": "CineVerse Portal del Rio", "room": "Sala Brisa", "price": 18500, "format": "2D"},
            {"offset_days": 1, "time": "16:40:00", "city": "Medellin", "venue": "CineVerse El Tesoro", "room": "Sala Bosque", "price": 19000, "format": "VIP"},
        ],
    },
    {
        "titulo": "Mickey 17",
        "descripcion": "Un trabajador clonable descubre que su identidad vale mas que la mision espacial que lo consume.",
        "duracion": 139,
        "genero": "Suspenso",
        "categoria": "Tendencias",
        "clasificacion": "+13",
        "imagen_url": "/static/img/posters/mickey-17.svg",
        "trailer_url": "",
        "funciones": [
            {"offset_days": 0, "time": "19:00:00", "city": "Barranquilla", "venue": "CineVerse Buenavista", "room": "Sala Zero", "price": 20500, "format": "2D"},
            {"offset_days": 1, "time": "20:40:00", "city": "Bucaramanga", "venue": "CineVerse Cacique", "room": "Sala Zero", "price": 21000, "format": "IMAX"},
        ],
    },
    {
        "titulo": "Nosferatu",
        "descripcion": "Una joven queda atrapada por la obsesion de una criatura antigua que vuelve a la ciudad en sombras.",
        "duracion": 133,
        "genero": "Terror",
        "categoria": "Noches de terror",
        "clasificacion": "+18",
        "imagen_url": "/static/img/posters/nosferatu.svg",
        "trailer_url": "",
        "funciones": [
            {"offset_days": 0, "time": "22:00:00", "city": "Barranquilla", "venue": "CineVerse Buenavista", "room": "Sala Eclipse", "price": 23000, "format": "2D"},
            {"offset_days": 1, "time": "21:30:00", "city": "Cartagena", "venue": "CineVerse Caribe Plaza", "room": "Sala Eclipse", "price": 23500, "format": "VIP"},
        ],
    },
    {
        "titulo": "Flow",
        "descripcion": "Un grupo de animales navega un mundo inundado en una aventura silenciosa y emotiva.",
        "duracion": 85,
        "genero": "Drama",
        "categoria": "Festival",
        "clasificacion": "+7",
        "imagen_url": "/static/img/posters/flow.svg",
        "trailer_url": "",
        "funciones": [
            {"offset_days": 0, "time": "18:00:00", "city": "Barranquilla", "venue": "CineVerse Buenavista", "room": "Sala Aurora", "price": 18000, "format": "2D"},
            {"offset_days": 1, "time": "17:00:00", "city": "Bogota", "venue": "CineVerse Andino", "room": "Sala Aurora", "price": 18500, "format": "VIP"},
        ],
    },
    {
        "titulo": "Mision Imposible: Sentencia Final",
        "descripcion": "Ethan Hunt encara una amenaza global con una mision que no permite margen de error.",
        "duracion": 148,
        "genero": "Accion",
        "categoria": "Estreno",
        "clasificacion": "+13",
        "imagen_url": "/static/img/posters/mision-imposible-sentencia-final.svg",
        "trailer_url": "",
        "funciones": [
            {"offset_days": 2, "time": "18:15:00", "city": "Bogota", "venue": "CineVerse Gran Estacion", "room": "Sala Vision", "price": 24000, "format": "IMAX"},
            {"offset_days": 2, "time": "20:45:00", "city": "Barranquilla", "venue": "CineVerse Buenavista", "room": "Sala Vision", "price": 23000, "format": "VIP"},
        ],
    },
]
