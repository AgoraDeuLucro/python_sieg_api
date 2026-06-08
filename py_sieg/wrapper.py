import io
import zipfile
from time import sleep
from datetime import datetime, date
import requests


class auth():

    def __init__(self, client_id, secret_key, token_api, jwt=None, base_url="https://api.sieg.com", print_error=True):
        self.client_id = client_id
        self.secret_key = secret_key
        self.token_api = token_api
        self.jwt = jwt
        self.base_url = base_url
        self.print_error = print_error

    def create_jwt(self):
        url = f"{self.base_url}/api/v1/create-jwt"
        headers = {
            "X-Client-Id": self.client_id,
            "X-Secret-Key": self.secret_key,
        }
        limite = 20
        tentativas = 0

        while True:
            try:
                response = requests.post(url, headers=headers)
            except Exception as e:
                tentativas += 1
                if self.print_error:
                    print(f"Erro na requisição ({tentativas}/{limite}): {e}")
                if tentativas >= limite:
                    return None
                sleep(30)
                continue

            if response.status_code == 200:
                self.jwt = response.json()
                return self.jwt
            else:
                tentativas += 1
                if self.print_error:
                    print(
                        f"Erro {response.status_code} em create-jwt "
                        f"({tentativas}/{limite}): {response.text[:200]}"
                    )
                if tentativas >= limite:
                    return None
                sleep(30)

    def request(self, endpoint, body):
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.token_api,
        }
        if self.jwt:
            headers["Authorization"] = f"Bearer {self.jwt}"

        limite = 20
        tentativas = 0

        while True:
            try:
                response = requests.post(url, json=body, headers=headers)
            except Exception as e:
                tentativas += 1
                if self.print_error:
                    print(f"Erro na requisição ({tentativas}/{limite}): {e}")
                if tentativas >= limite:
                    return None
                sleep(30)
                continue

            if response.status_code == 200:
                return response
            elif response.status_code == 404:
                return response
            elif response.status_code == 504:
                return response
            else:
                tentativas += 1
                if self.print_error:
                    print(
                        f"Erro {response.status_code} em {endpoint} "
                        f"({tentativas}/{limite}): {response.text[:200]}"
                    )
                if tentativas >= limite:
                    return None
                sleep(30)


class xmls(auth):

    XML_TYPES = {
        "NFe": 1,
        "CTe": 2,
        "NFSe": 3,
        "NFCe": 4,
        "CFe": 5,
    }

    def _fmt_date(self, d, end_of_day=False, date_only=False):
        if isinstance(d, datetime):
            if date_only:
                return d.date().isoformat()
            return d.isoformat()
        if isinstance(d, date):
            if date_only:
                return d.isoformat()
            time_part = "23:59:59" if end_of_day else "00:00:00"
            return f"{d.isoformat()}T{time_part}"
        s = str(d)
        if len(s) == 10:
            if date_only:
                return s
            time_part = "23:59:59" if end_of_day else "00:00:00"
            return f"{s}T{time_part}"
        return s

    def _resolve_xml_type(self, xml_type):
        if isinstance(xml_type, str):
            if xml_type not in self.XML_TYPES:
                raise ValueError(
                    f"xml_type inválido: '{xml_type}'. "
                    f"Valores aceitos: {list(self.XML_TYPES.keys())} ou inteiros 1–5."
                )
            return self.XML_TYPES[xml_type]
        return int(xml_type)

    def _extract_zip(self, content):
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            return [zf.read(name) for name in zf.namelist()]

    def contar(self, date_start, date_end, **kwargs):
        body = {
            "DataEmissaoInicio": self._fmt_date(date_start),
            "DataEmissaoFim": self._fmt_date(date_end, end_of_day=True),
        }
        body.update(kwargs)

        response = self.request("api/v1/contar-xmls", body)

        if response and response.status_code == 200:
            return response.json().get("Data", {})
        return {}

    def baixar(self, date_start, date_end, xml_type, take=None, skip=None, decode=False, **kwargs):
        tipo = self._resolve_xml_type(xml_type)
        date_only = tipo == self.XML_TYPES["NFSe"]
        body = {
            "DataEmissaoInicio": self._fmt_date(date_start, date_only=date_only),
            "DataEmissaoFim": self._fmt_date(date_end, end_of_day=not date_only, date_only=date_only),
            "TipoXml": tipo,
        }

        if take is not None:
            body["Take"] = take
        if skip is not None:
            body["Skip"] = skip

        body.update(kwargs)

        response = self.request("api/v1/baixar-xmls", body)

        if response is None or response.status_code == 404:
            return [] if decode else b""
        if response.status_code == 504:
            if self.print_error:
                print("Gateway Time-out: muitos XMLs para o período solicitado. Use paginação (take/skip).")
            return [] if decode else b""
        if response.status_code != 200:
            return [] if decode else b""

        if decode:
            return self._extract_zip(response.content)
        return response.content

    def baixar_por_chave(self, chave_xml, xml_type, baixar_eventos=False, decode=False, **kwargs):
        body = {
            "ChaveXml": chave_xml,
            "TipoXml": self._resolve_xml_type(xml_type),
            "BaixarEventos": baixar_eventos,
        }
        body.update(kwargs)

        response = self.request("api/v1/baixar-xml", body)

        if response is None or response.status_code == 404:
            return [] if decode else b""
        if response.status_code == 504:
            if self.print_error:
                print("Gateway Time-out ao baixar XML pela chave.")
            return [] if decode else b""
        if response.status_code != 200:
            return [] if decode else b""

        if decode:
            return self._extract_zip(response.content)
        return response.content

    def baixar_eventos(self, date_start, date_end, xml_type, tipo_evento=None, take=None, skip=None, decode=False, **kwargs):
        tipo = self._resolve_xml_type(xml_type)
        date_only = tipo == self.XML_TYPES["NFSe"]
        body = {
            "DataInicioEvento": self._fmt_date(date_start, date_only=date_only),
            "DataFimEvento": self._fmt_date(date_end, end_of_day=not date_only, date_only=date_only),
            "TipoXml": tipo,
        }

        if tipo_evento is not None:
            body["TipoEvento"] = tipo_evento
        if take is not None:
            body["Take"] = take
        if skip is not None:
            body["Skip"] = skip

        body.update(kwargs)

        response = self.request("api/v1/baixar-eventos", body)

        if response is None or response.status_code == 404:
            return [] if decode else b""
        if response.status_code == 504:
            if self.print_error:
                print("Gateway Time-out: muitos eventos para o período solicitado. Use paginação (take/skip).")
            return [] if decode else b""
        if response.status_code != 200:
            return [] if decode else b""

        if decode:
            return self._extract_zip(response.content)
        return response.content
