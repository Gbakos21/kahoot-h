import ctypes, json, random, requests, time, urllib.parse
from Kahoot import kahootReceive, kahootPayload, kahootError
from requests.packages.urllib3.exceptions import InsecureRequestWarning
# import os, sys, inspect
# cmd_subfolder = os.path.realpath(os.path.abspath(os.path.join(os.path.split(inspect.getfile( inspect.currentframe() ))[0],"lib")))
# if cmd_subfolder not in sys.path:
#     sys.path.insert(0, cmd_subfolder)
class kahootSend:
    def __init__(self, kahoot):
        self.kahoot = kahoot
        self.variables = self.kahoot.variables
        self.headers = self.variables.headers
        self.payloads = kahootPayload.makePayloads(self.variables)
        self._ansi_enabled = False
        self._last_question = None
        self._last_choices = []
        self._answered_questions = set()
        self._last_game_block_id = None
        self._enableAnsiColors()
        if (self.variables.debugLevel < 5) and not self.variables.verify:
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    def _enableAnsiColors(self):
        if self._ansi_enabled:
            return
        try:
            handle = ctypes.windll.kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass
        self._ansi_enabled = True

    def _color(self, text, code):
        return "\033[" + str(code) + "m" + str(text) + "\033[0m"

    def _debugAuto(self, message):
        if getattr(self.variables, 'debugLevel', 0) >= 2:
            print(self._color("[auto]", 90), str(message))

    def _resolveCorrectAnswers(self, answers):
        resolved = []
        if not isinstance(answers, list):
            return resolved

        for answer in answers:
            answer_index = None
            if isinstance(answer, int):
                answer_index = answer
            elif isinstance(answer, str) and answer.isdigit():
                answer_index = int(answer)
            elif isinstance(answer, dict):
                if 'answer' in answer:
                    resolved.append(str(answer['answer']))
                    continue
                if ('choice' in answer) and isinstance(answer['choice'], int):
                    answer_index = answer['choice']

            if answer_index is None:
                resolved.append(str(answer))
                continue

            if (answer_index >= 0) and (answer_index < len(self._last_choices)):
                choice_text = self._last_choices[answer_index]
                if choice_text:
                    resolved.append(str(choice_text))
                else:
                    resolved.append("option " + str(answer_index + 1))
            else:
                resolved.append("option " + str(answer_index + 1))
        return resolved

    def _tryAutoAnswer(self, content_data):
        question_index = content_data.get('questionIndex')
        if not isinstance(question_index, int):
            question_index = content_data.get('gameBlockIndex')
        if not isinstance(question_index, int):
            self._debugAuto("skip: missing questionIndex/gameBlockIndex in id:2 payload")
            return

        try:
            number_of_choices = int(content_data.get('numberOfChoices'))
        except Exception:
            self._debugAuto("skip: numberOfChoices missing or invalid")
            return

        if number_of_choices <= 0:
            self._debugAuto("skip: numberOfChoices <= 0")
            return
        if question_index in self._answered_questions:
            self._debugAuto("skip: already answered question #" + str(question_index + 1))
            return

        answer_choice = random.randrange(number_of_choices)
        try:
            self.sendAnswer(answer_choice)
            self._answered_questions.add(question_index)
            print(self._color("Auto answer sent:", 95), self._color("Question #" + str(question_index + 1) + " -> option " + str(answer_choice + 1), 93))
        except Exception as e:
            self._debugAuto("send failed: " + str(e))
            return

    def _printQuestionAndAnswer(self, raw_text):
        try:
            payload = json.loads(raw_text)
        except Exception:
            return
        if not isinstance(payload, list):
            return

        for item in payload:
            if not isinstance(item, dict):
                continue
            if item.get('channel') != "/service/player":
                continue
            data = item.get('data', {})
            if not isinstance(data, dict):
                continue
            data_id = data.get('id')
            try:
                data_id = int(data_id)
            except Exception:
                data_id = -1
            content = data.get('content')
            if not isinstance(content, str):
                continue

            try:
                content_data = json.loads(content)
            except Exception:
                continue

            if data_id == 9:
                question_block = content_data.get('firstGameBlockData', {})
                if not isinstance(question_block, dict):
                    continue

                game_block_id = content_data.get('gameId')
                if game_block_id and game_block_id != self._last_game_block_id:
                    self._answered_questions = set()
                    self._last_game_block_id = game_block_id

                question = question_block.get('question')
                choices = question_block.get('choices', [])
                if question:
                    self._last_question = str(question)
                    print(self._color("\nQuestion:", 96), self._color(question, 94))

                self._last_choices = []
                if isinstance(choices, list):
                    for choice in choices:
                        if isinstance(choice, dict):
                            self._last_choices.append(choice.get('answer'))
                        else:
                            self._last_choices.append(None)

                correct_answers = []
                if isinstance(choices, list):
                    for choice in choices:
                        if isinstance(choice, dict) and choice.get('correct') == True:
                            answer = choice.get('answer')
                            if answer is not None:
                                correct_answers.append(str(answer))

                if len(correct_answers) > 0:
                    print(self._color("Correct answer:", 92), self._color(", ".join(correct_answers), 93))
                continue

            if data_id == 1:
                question_index = content_data.get('questionIndex')
                number_of_choices = content_data.get('numberOfChoices')
                if isinstance(question_index, int):
                    self._last_question = "Question #" + str(question_index + 1)
                    print(self._color("\nQuestion start:", 96), self._color(self._last_question, 94))
                else:
                    self._last_question = None

                if isinstance(number_of_choices, int) and number_of_choices >= 0:
                    self._last_choices = [None] * number_of_choices
                else:
                    self._last_choices = []
                continue

            if data_id == 2:
                self._tryAutoAnswer(content_data)
                continue

            if data_id == 8:
                resolved = self._resolveCorrectAnswers(content_data.get('correctAnswers', []))
                if self._last_question:
                    print(self._color("\nRound question:", 96), self._color(self._last_question, 94))
                if len(resolved) > 0:
                    print(self._color("Round correct:", 92), self._color(", ".join(resolved), 93))

    def setHeaders(self, headers):
        self.headers = headers
    def processResponse(self, r, statusCodePass=200):
        if r.status_code != statusCodePass:
            raise kahootError.kahootError(r.url+' returned http error code ' + str(r.status_code) )
        try:
            response = json.loads(r.text)
            for x in response:
                if "successful" in x:
                    if x["successful"] != True:
                        raise kahootError.kahootError(r.url+' returned an unsuccessful response')
                if ('ext' in x) and ('timesync' in x['ext']):
                    self.variables.setPrevTcl(x['ext']['timesync'])
            return response
        except Exception as e:
            if self.variables.debugLevel > 2:
                print(e)
                print(r.text)
            raise kahootError.kahootError('The response from '+ r.url +' was unparseable')
    def checkResponse(self, r, statusCodePass=200, statusCodeFail=0):
        if r == None:
            raise kahootError.kahootError(self.variables.domain+' returned nothing' )
        if (r.status_code != statusCodePass) and (r.status_code != statusCodeFail):
            raise kahootError.kahootError(self.variables.domain+' returned http error code ' + str(r.status_code) )
        return r
    def send(self, dataIn, urlExt=''):
        data = str(dataIn)
        httpSession = self.variables.httpSession
        url = self.variables.getUrl(urlExt)
        try:
            r = httpSession.post(url, data=dataIn, headers=self.headers, verify=self.variables.verify)
            if self.variables.debug:
                print("\n\n\ndata:",dataIn,"\nText:", r.text)
                self._printQuestionAndAnswer(r.text)
            return r
        except requests.exceptions.ConnectionError:
            print(self.variables.domain+' refused the connection')
    def get(self, url, timeout=None):
        httpSession = self.variables.httpSession
        try:
            kwargs = {'headers': self.headers, 'verify': self.variables.verify}
            if timeout is not None:
                kwargs['timeout'] = timeout
            r = httpSession.get(url, **kwargs)
            if self.variables.debug:
                print("\n\n\nurl:",url,"\nText:", r.text)
                self._printQuestionAndAnswer(r.text)
            return r
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return None
    def connect(self):
        data = self.payloads.connection()
        r = self.send(data, 'connect')
        self.kahoot.queue.add(self.connect)
        response = self.processResponse(r)
        self.kahoot.process.connect(response)
        return response
    def firstConnect(self):
        data = self.payloads.firstConnection()
        r = self.send(data, 'connect')
        self.kahoot.queue.add(self.connect)
        response = self.processResponse(r)
        self.kahoot.process.connect(response)
        return response
    def handshake(self):
        data = self.payloads.handshake()
        r = self.send(data, 'handshake')
        return self.processResponse(r)
    def subscribeOnce(self, service, channel):
        r = self.send(self.payloads.subscribe(service, channel), 'subscribe')
        return self.processResponse(r)
    def subscribe(self):
        channels_to_sub = ["subscribe"] #["subscribe", "unsubscribe", "subscribe"]
        services_to_sub = ["controller", "player", "status"]
        for channel in channels_to_sub:
            for service in services_to_sub:
                self.subscribeOnce(service, channel)
    def sessionStart(self):
        url = self.variables.getUrl()
        r = self.get(url)
        return self.checkResponse(r, 400).text
    def testSession(self):
        url = self.variables.getReserveUrl()
        r = self.get(url)
        return self.checkResponse(r, statusCodeFail=404)
    def solveKahootChallenge(self, dataChallenge):
        htmlDataChallenge = urllib.parse.quote_plus(str(dataChallenge))
        url = "http://safeval.pw/eval?code="+htmlDataChallenge
        attempt = 1
        maxAttemps = 5
        r = self.get(url, timeout=self.variables.timeoutTime)
        while (r == None) and (attempt < maxAttemps):
            attempt = attempt + 1
            r = self.get(url, timeout=self.variables.timeoutTime)
            time.sleep(self.variables.timeoutTime)
        if r == None:
            if self.variables.debugLevel >= 1:
                print("name:",self.variables.name ,"unsucsessful:",url)
            raise kahootError.kahootError('Tried to solve the chalenge but unsucsessful after '+str(attempt)+' attemps')
        return self.checkResponse(r)
    def sendName(self):
        r = self.send(self.payloads.name())
        data = self.processResponse(r)
        self.kahoot.process.checkConnected(data)
        return data
    def sendAnswer(self, choice):
        payload = self.payloads.answer(choice)
        r = self.send(payload)
        return self.checkResponse(r, statusCodeFail=404)
