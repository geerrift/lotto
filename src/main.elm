import Browser
import Browser.Navigation as Nav
import Html exposing (..)
import Html.Attributes exposing (..)
import Html.Events exposing (..)
import Url
import Url.Parser as UP exposing ((</>))
import Json.Decode as JD exposing (Decoder, field, string)
import Http
import Dict
import List exposing (..)

{- TODO
   - Makescript

   - Make backend
   - Home status: lottery running?

   - Deal with loading
   - OpenID Connect
   - Vouchers, status, expiration
   - transfers
   - gifts

-}


type alias QuestionSets = List QuestionSet
type alias Model = { key : Nav.Key, url : Url.Url, route : Maybe Route, questions: Maybe QuestionSets, registered : Bool}

type HttpResource t = Failure Http.Error | Loading | Success t
type Route = Home | Questions Int | Register
type Msg
  = LinkClicked Browser.UrlRequest
  | UrlChanged Url.Url
  | GetQuestions
  | GotQuestions (Result Http.Error (List QuestionSet))
  | Registered

main = Browser.application { init = init, view = view, update = update, subscriptions = subscriptions
                           , onUrlChange = UrlChanged, onUrlRequest = LinkClicked }

init : () -> Url.Url -> Nav.Key -> ( Model, Cmd Msg )
init flags url key = ( Model key url (Just Home) Nothing False, Cmd.none )

routeParser : UP.Parser (Route -> a) a
routeParser =
    UP.oneOf
        [ UP.map Home UP.top
          , UP.map Questions (UP.s "questions" </> UP.int)
          , UP.map Register (UP.s "register")
        ]

update : Msg -> Model -> ( Model, Cmd Msg )
update msg model =
  case msg of
    LinkClicked urlRequest ->
      case urlRequest of
        Browser.Internal url ->
            ( model, Nav.pushUrl model.key (Url.toString url) )

        Browser.External href ->
          ( model, Nav.load href )

    UrlChanged url ->
      ( { model | url = url
                  , route = UP.parse routeParser url }
      , Cmd.none
      )
    GetQuestions -> ( model, getQuestions ) -- TODO loading
    GotQuestions result ->
        case result of
            Ok qs -> ( { model | questions = Just qs }, Cmd.none )
            Err _ -> ( model, Cmd.none ) -- TODO error
    Registered -> ( { model | registered = True }, Cmd.none )

subscriptions : Model -> Sub Msg
subscriptions _ =
  Sub.none

mkTitle : String -> String
mkTitle t = "Borderland 2019 - " ++ t

view : Model -> Browser.Document Msg
view model =
    case model.route of
        Just Home -> { title = mkTitle "Lottery"
                     , body = viewHome model }
        Just Register -> { title = mkTitle "Registering"
                         , body = [ div [] [ text "You're about to enter the wonderful world of registrering."]
                                  , a [ onClick GetQuestions, href "/questions/0" ] [ text "Aks me questions?" ] ] }
        Just (Questions int) -> { title = mkTitle "Questions?"
                                , body = viewQuestionSet model int }
        Nothing -> { title = mkTitle "You're lost", body = [ text "You're in a maze of websites, all alike." ] }

viewHome : Model -> List (Html msg)
viewHome model = if model.registered then
                     [ text "you're lottery registered" ]
                 else
                     [ div [ class "registerText" ] [ text "Blah blah" ],
                           a [ href "/register" ] [ text "Register!" ] ]

viewQuestionSet : Model -> Int -> List (Html Msg)
viewQuestionSet m i =
    case m.questions of
        Just ql ->
            case (head (drop i ql)) of
                Just qs -> [ text qs.description
                           , text (String.fromInt (length ql))
                           , viewQuestions qs.questions
                           , if ((i+1) >= length ql) then
                                 (a [ href "/", onClick Registered ] [ text "done" ])
                             else
                                 (a [ href ("/questions/" ++ (String.fromInt (i+1))) ] [ text "next!" ]) ]
                Nothing -> [ text "cool" ]
        Nothing -> [ text "what" ]

viewQuestions : List Question -> Html msg
viewQuestions qs = div [] (List.map viewQuestion qs)

viewQuestion : Question -> Html msg
viewQuestion q = div [ class q.tag ] [
                  text q.question
                  , input [ type_ "text", value q.answer ] [ ]
                 ]

getQuestions : Cmd Msg
getQuestions = Http.get
               { url = "/mock-data/questions.json"
               , expect = Http.expectJson GotQuestions questionsDecoder }

type alias QuestionSet = { tag: String, heading: String, description : String, questions : List Question }
type alias Question = { tag : String, question : String, qType : String, answer : String }
questionsDecoder : JD.Decoder (List QuestionSet)
questionsDecoder = JD.list (
                   JD.map4 QuestionSet
                       (JD.at ["tag"] JD.string)
                       (JD.at ["heading"] JD.string)
                       (JD.at ["description"] JD.string)
                       (JD.at ["questions"] (JD.list
                            (JD.map4 Question
                                 (JD.at ["tag"] JD.string)
                                 (JD.at ["question"] JD.string)
                                 (JD.at ["type"] JD.string)
                                 (JD.at ["answer"] JD.string)
                            ))))

