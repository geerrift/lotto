import Browser
import Browser.Navigation as Nav
import Html exposing (..)
import Html.Attributes exposing (..)
import Html.Events exposing (..)
import Url
import Url.Parser as UP exposing ((</>))
import Json.Decode as JD exposing (Decoder, field, string)
import Json.Decode.Extra
import Json.Encode
import Http
import Dict exposing (Dict)
import List exposing (..)
import Time

{- TODO
   - Preload questions
   - OpenID Connect
   - Vouchers, status, expiration
   - transfers
   - gifts
   - input validation
   - Question options: remember selection
   - date picker
-}


type alias Question
    = { id : Int
      , question : String
      , answer : String
      , options: List String }

type alias Questions
    = { description : String
      , id : Int
      , name : String
      , questions : List Question }

type alias Lottery
    = { can_register : Bool
      , can_transfer : Bool
      , questions : List Int }

type alias Voucher
    = { code : String
      , expires : Time.Posix }

type alias Registration
    = { registered : Bool
      , vouchers : List Voucher }

type alias Model
    = { key : Nav.Key
      , url : Url.Url
      , route : Maybe Route
      , questionSets: Dict Int Questions
      , lottery: Lottery
      , registration: Registration }

type alias HttpResource t = Result Http.Error t

type Route
    = Home
    | QuestionPage Int
    | RegisterPage

type Msg
  = LinkClicked Browser.UrlRequest
  | UrlChanged Url.Url
  | GetQuestions Int
  | GetLottery
  | GetRegistration
  | GotQuestions (HttpResource Questions)
  | GotLottery (HttpResource Lottery)
  | GotRegistration (HttpResource Registration)
  | UpdateAnswer Int Question String
  | PostAnswers Questions Bool

main =
    Browser.application
       { init = init
       , view = view
       , update = update
       , subscriptions = subscriptions
       , onUrlChange = UrlChanged
       , onUrlRequest = LinkClicked }

init : () -> Url.Url -> Nav.Key -> ( Model, Cmd Msg )
init flags url key
    = ( Model
            key
            url
            (UP.parse routeParser url) -- fixme
            Dict.empty
            (Lottery False False [])
            (Registration False [])
      , Cmd.batch [ getLottery , getRegistration ] )

routeParser : UP.Parser (Route -> a) a
routeParser =
    UP.oneOf
        [ UP.map Home UP.top
          , UP.map QuestionPage (UP.s "questions" </> UP.int)
          , UP.map RegisterPage (UP.s "register")
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
      , Cmd.none )

    GetQuestions i ->
        ( model, getQuestions i ) -- TODO loading

    GetLottery ->
        ( model, getLottery )

    GetRegistration ->
        ( model, getRegistration )

    GotQuestions result ->
        case result of
            Ok qs -> ( { model | questionSets = Dict.insert qs.id qs model.questionSets }, Cmd.none )
            Err _ -> ( model, Cmd.none ) -- TODO error

    GotLottery result ->
        case result of
            Ok l -> ( { model | lottery = l }, Cmd.none )
            Err _ -> ( model, Cmd.none )

    GotRegistration result ->
        case result of
            Ok r -> ( { model | registration = r }, Cmd.none )
            Err _ -> ( model, Cmd.none )

    PostAnswers qs last ->
        ( model
        , Cmd.batch
            ([ postAnswers qs ] ++
                 if last then
                     [ postRegistration ]
                 else
                     [ getQuestions (qs.id+1) ]))

    UpdateAnswer set q v -> -- welp FIXME fix model
        let
            qs = Maybe.withDefault
                 { description = ""
                 , id = -1
                 , name = ""
                 , questions = []}
                 (Dict.get set model.questionSets)
            updateAnswer oldQ = if (q.id == oldQ.id) then { q | answer = v } else oldQ
            newQuestions = List.map updateAnswer qs.questions
            newQs = Dict.update set (\_ ->
                                         Just { qs | questions = newQuestions })
                    model.questionSets
        in
            ( { model | questionSets = newQs } , Cmd.none )

subscriptions : Model -> Sub Msg
subscriptions _ =
  Sub.none

mkTitle : String -> String
mkTitle t = "Borderland 2019 - " ++ t

view : Model -> Browser.Document Msg
view model =
    case model.route of
        Just Home ->
            { title =
                  mkTitle "Lottery"
            , body =
                viewHome model }

        Just RegisterPage -> { title =
                                   mkTitle "Registering"
                             , body =
                                   [ div [] [ text "You're about to enter the wonderful world of registrering."]
                                   , a [ onClick (GetQuestions 1), href "/questions/1" ] [ text "Aks me questions?" ] ] }

        Just (QuestionPage int) ->
            { title =
                  mkTitle "Questions?" -- TODO
            , body =
                [ viewQuestionSet model int ] }

        Nothing -> { title = mkTitle "You're lost", body = [ text "You're in a maze of websites, all alike." ] }

viewHome : Model -> List (Html Msg)
viewHome model =
    [ div [] [ h1 [] [ text "Borderland Registraton"]] ]  ++
    [ viewRegistrationStatus model ]

viewRegistrationStatus : Model -> Html Msg
viewRegistrationStatus model =
    if model.registration.registered then
        div [] [
            text "You're registered!"
            , a [ href "/register" ] [ text "Change your answers."] ]
    else
        div []
            [ text "Click here to register for Borderland 2019: "
            , a [ href "/register" ] [ text "Register"]
            ]

viewQuestionSet : Model -> Int -> Html Msg
viewQuestionSet model i =
    case Dict.get i model.questionSets of
        Just qs ->
            let
                rem = List.filter (\e -> e > qs.id ) model.lottery.questions
            in
                viewQuestions qs (if List.isEmpty rem then
                                      [ href "/", onClick (PostAnswers qs True) ]
                                  else
                                      [ href ("/questions/" ++ String.fromInt(qs.id + 1))
                                           , onClick (PostAnswers qs False) ] )
        Nothing ->
            text ""  -- TODO

viewQuestions : Questions -> List (Attribute Msg) -> Html Msg
viewQuestions qs next = div []
                        ([ h1 [] [ text qs.name ]
                        , text qs.description
                        ] ++ List.map (viewQuestion qs.id) qs.questions
                        ++ [ a next [ text "Next" ] ])

viewQuestion : Int -> Question -> Html Msg
viewQuestion set q =
    let
        qId = "question-" ++ (String.fromInt q.id)
    in
        div [ class "q" ]
                 ( if List.isEmpty q.options then
                       [
                        label [ for qId ] [ text q.question ]
                       , input [ type_ "text", id qId, value q.answer, onInput (UpdateAnswer set q) ] []
                       ]
                 else
                     [
                      label [ for qId ] [ text q.question ]
                     ] ++ (List.map viewOption q.options))

viewOption : String -> Html Msg
viewOption desc =
    div [] -- TODO
        [ input [ type_ "checkbox", id desc ] []
        , label [ for desc ] [ text desc ]
        ]

-- HTTP resources

getQuestions : Int -> Cmd Msg
getQuestions i = Http.get
               { url = "/api/questions/" ++ String.fromInt(i)
               , expect = Http.expectJson GotQuestions questionsDecoder }

postAnswers : Questions -> Cmd Msg
postAnswers qs = Http.post
                { url = "/api/questions/" ++ String.fromInt(qs.id)
                , body = Http.multipartBody
                         (List.map (\q -> Http.stringPart (String.fromInt q.id) q.answer)
                              qs.questions)
                , expect = Http.expectJson GotQuestions questionsDecoder }

getRegistration : Cmd Msg
getRegistration = Http.get
               { url = "/api/registration"
               , expect = Http.expectJson GotRegistration registrationDecoder }

postRegistration : Cmd Msg
postRegistration = Http.post
               { url = "/api/registration"
               , body = Http.emptyBody
               , expect = Http.expectJson GotRegistration registrationDecoder }

getLottery : Cmd Msg
getLottery = Http.get
               { url = "/api/lottery"
               , expect = Http.expectJson GotLottery lotteryDecoder }

-- JSON Decoders

questionsDecoder : JD.Decoder Questions
questionsDecoder = JD.map4 Questions
                      (JD.at ["description"] JD.string)
                      (JD.at ["id"] JD.int)
                      (JD.at ["name"] JD.string)
                      (JD.at ["questions"] (JD.list
                           (JD.map4 Question
                                (JD.at ["id"] JD.int)
                                (JD.at ["question"] JD.string)
                                (JD.at ["answer"] JD.string)
                                (JD.at ["options"] (JD.list JD.string)))))

lotteryDecoder : JD.Decoder Lottery
lotteryDecoder = JD.map3 Lottery
                    (JD.at ["can_register"] JD.bool)
                    (JD.at ["can_transfer"] JD.bool)
                    (JD.at ["questions"] (JD.list JD.int))

voucherDecoder : JD.Decoder Voucher
voucherDecoder = JD.map2 Voucher
                    (JD.at ["code"] JD.string)
                    (JD.at ["expires"] Json.Decode.Extra.datetime)

registrationDecoder : JD.Decoder Registration
registrationDecoder = JD.map2 Registration
                        (JD.at ["registered"] JD.bool)
                        (JD.at ["vouchers"] (JD.list voucherDecoder))
