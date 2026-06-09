import io
import zipfile
import base64
import json
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

    def _extract_xmls_from_json(self, content):
        try:
            data = json.loads(content)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        is_api_json = any(key in data for key in ("Data", "IsSuccess", "IsFailure", "StatusCode"))
        xmls_list = []

        def decode_b64(val):
            try:
                if isinstance(val, str):
                    val = val.strip()
                    missing_padding = len(val) % 4
                    if missing_padding:
                        val += '=' * (4 - missing_padding)
                    return base64.b64decode(val)
            except Exception:
                pass
            return None

        def process_decoded_payload(decoded_bytes):
            if not decoded_bytes:
                return
            if decoded_bytes.startswith(b'PK\x03\x04'):
                try:
                    xmls_list.extend(self._extract_zip(decoded_bytes))
                except Exception:
                    pass
            else:
                xmls_list.append(decoded_bytes)

        def process_value(val):
            if not isinstance(val, str):
                return
            val = val.strip()
            if not val:
                return
            if val.startswith('<'):
                xmls_list.append(val.encode('utf-8'))
                return
            decoded = decode_b64(val)
            if decoded:
                process_decoded_payload(decoded)

        def process_item(item):
            if isinstance(item, str):
                process_value(item)
            elif isinstance(item, dict):
                for key in ["Data", "data", "Xml", "xml", "Conteudo", "conteudo", "Content", "content", "Base64", "base64", "XmlBase64"]:
                    val = item.get(key)
                    if val:
                        if isinstance(val, str):
                            process_value(val)
                        elif isinstance(val, list):
                            for sub_item in val:
                                process_item(sub_item)
                        break

        # 1. Campo "Data" — resposta padrão de /api/v1/baixar-xml (XML em texto)
        data_field = data.get("Data")
        if data_field is not None:
            if isinstance(data_field, str):
                process_value(data_field)
            elif isinstance(data_field, list):
                for item in data_field:
                    process_item(item)
            elif isinstance(data_field, dict):
                process_item(data_field)

        # 2. Campo "Xml" (base64 ou texto)
        xml_field = data.get("Xml") or data.get("xml")
        if xml_field:
            if isinstance(xml_field, str):
                process_value(xml_field)
            elif isinstance(xml_field, list):
                for item in xml_field:
                    process_item(item)

        # 3. Campo "Xmls" (lista de strings ou objetos)
        xmls_field = data.get("Xmls") or data.get("xmls")
        if isinstance(xmls_field, list):
            for item in xmls_field:
                process_item(item)

        # 4. Campo "Arquivo" (base64 zip ou xml)
        arquivo_field = data.get("Arquivo") or data.get("arquivo")
        if arquivo_field and isinstance(arquivo_field, str):
            process_value(arquivo_field)

        # 5. Campo "Conteudo" / "Content"
        conteudo_field = data.get("Conteudo") or data.get("conteudo") or data.get("Content") or data.get("content")
        if conteudo_field and isinstance(conteudo_field, str):
            process_value(conteudo_field)

        if xmls_list:
            return xmls_list
        if is_api_json:
            return []
        return None

    def _decode_response(self, content):
        extracted = self._extract_xmls_from_json(content)
        if extracted is not None:
            return extracted
        try:
            return self._extract_zip(content)
        except Exception as e:
            if self.print_error:
                print(f"Erro ao extrair ZIP: {e}")
            return []

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
            return self._decode_response(response.content)
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
            return self._decode_response(response.content)
        return response.content

    def baixar_eventos(self, date_start, date_end, xml_type, chave_xml=None, tipo_evento=None, take=None, skip=None, decode=False, **kwargs):
        tipo = self._resolve_xml_type(xml_type)
        date_only = tipo == self.XML_TYPES["NFSe"]
        body = {
            "DataInicioEvento": self._fmt_date(date_start, date_only=date_only),
            "DataFimEvento": self._fmt_date(date_end, end_of_day=not date_only, date_only=date_only),
            "TipoXml": tipo,
        }

        if chave_xml is not None:
            body["ChaveXml"] = chave_xml
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
            return self._decode_response(response.content)
        return response.content
