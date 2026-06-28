from pydantic import BaseModel


class OpcionQuiz(BaseModel):
    letra: str   # "a" | "b" | "c" | "d"
    texto: str
    correcta: bool


class PreguntaQuiz(BaseModel):
    numero: int
    pregunta: str
    opciones: list[OpcionQuiz]  # exactly 4
    explicacion: str


class SalidaExaminador(BaseModel):
    titulo: str
    preguntas: list[PreguntaQuiz]
