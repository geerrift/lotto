port module Main exposing (..)
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
import List exposing (..)
import Dict exposing (..)
import Set exposing (..)
import Time
import Http
import Debug

--

port renderButtons : () -> Cmd msg
port kcToken : (String -> msg) -> Sub msg

--

type alias Token = String
type QuestionType
    = Text
    | Date
    | MultipleChoice
    | DataList
    | Number

type alias Option
    = { id : Int
      , text : String }

type alias Question
    = { id : Int
      , text : String
      , answer : String
      , selections : Set Int
      , type_ : QuestionType
      , options: List Option }

type alias QuestionSet
    = { description : String
      , id : Int
      , priority : Int
      , questions : List Question
      , name : String }

type alias Lottery
    = { can_register : Bool
      , can_transfer : Bool
      , childItem : String
      , ticketItem : String
      , pretixUrl : String
      , questions : List Int }

type alias Voucher
    = { code : String
      , expires : Time.Posix }

type alias Ticket
    = { order: String
      , url: String }

type alias Registration
    = { registered : Bool
      , tickets : Maybe Ticket
      , email : String
      , vouchers : List Voucher }

type alias Model
    = { key : Nav.Key
      , url : Url.Url
      , route : Maybe Route
      , questionSets: List QuestionSet
      , questions : Dict Int Question
      , lottery: Lottery
      , registration: Maybe Registration
      , transfer_to : String
      , token: String
      , error: Maybe String
      , loading: Int }

type alias HttpResource t
    = Result Http.Error t

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
  | GotQuestionSet (HttpResource QuestionSet)
  | GotLottery (HttpResource Lottery)
  | GotRegistration (HttpResource Registration)
  | UpdateAnswer Int String
  | PostAnswers QuestionSet Bool
  | Posted (HttpResource ())
  | ToggleCheckbox Question Option Bool
  | TransferFieldInput String
  | TransferInvite Voucher
  | GiftTicket Voucher
  | RenderButtons
  | NewToken String
  | TicketGifted (HttpResource String)

--

main =
    Browser.application
       { init = init
       , view = view
       , update = update
       , subscriptions = subscriptions
       , onUrlChange = UrlChanged
       , onUrlRequest = LinkClicked }


init : String -> Url.Url -> Nav.Key -> ( Model, Cmd Msg )
init flags url key
    = ( Model
            key
            url
            (UP.parse routeParser url)
            []
            Dict.empty
            (Lottery False False "" "" "" [])
            Nothing
            ""
            flags
            Nothing
            2
      , Cmd.batch [ getLottery flags
                  , getRegistration flags ] )

routeParser : UP.Parser (Route -> a) a
routeParser =
    UP.oneOf
        [ UP.map Home UP.top
        , UP.map QuestionPage (UP.s "questions" </> UP.int)
        , UP.map RegisterPage (UP.s "register")
        ]

subscriptions : Model -> Sub Msg
subscriptions m =
    kcToken NewToken

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
        ( { model | loading = model.loading + 1 }, getQuestions model.token i )

    GetLottery ->
        ( { model | loading = model.loading + 1 }, getLottery model.token )

    GetRegistration ->
        ( { model | loading = model.loading + 1 }, getRegistration model.token )

    GotQuestionSet result ->
        case result of
            Ok qs ->
                  ( { model -- TODO maybe not keep adding forever, make immutable
                      | questionSets = (List.sortBy .priority (qs :: model.questionSets))
                      , questions = Dict.union model.questions <| Dict.fromList <| List.map (\q -> Tuple.pair q.id q) qs.questions
                      , loading = model.loading - 1
                  }
                , Cmd.none )
            Err e -> ( { model | error = Just <| decodeHttpError e
                               , loading = model.loading - 1
                       }, Cmd.none )

    GotLottery result ->
        case result of
            Ok l -> ( { model | lottery = l
                              , loading = model.loading - 1 + (List.length l.questions) }
                    , Cmd.batch (List.map
                                     (\q -> getQuestions model.token q)
                                     l.questions))
            Err e -> ( { model | error = Just <| decodeHttpError e
                               , loading = model.loading - 1 },
                           Cmd.none )

    GotRegistration result ->
        case result of
            Ok r -> ( { model | registration = Just r
                              , loading = model.loading - 1 }
                    , Cmd.none )
            Err e -> ( { model | error = Just <| decodeHttpError e
                               , loading = model.loading - 1 }
                     , Cmd.none )

    PostAnswers qs last ->
        ( { model | loading = model.loading + if last then 2 else 1 }
        , Cmd.batch
            ([ postAnswers model qs ] ++
                 if last then
                     [ postRegistration model.token ]
                 else
                     [])) --[ getQuestions model.token (qs.id+1) ]))

    UpdateAnswer id ans ->
        ( { model | questions = Dict.update id
                (\q ->
                     case q of
                         Just q_ -> Just { q_ | answer = ans }
                         Nothing -> Nothing)
                model.questions }
        , Cmd.none )

    ToggleCheckbox question option v ->
        let
            newQuestion = { question | selections =
                                -- if Set.member option.id question.selections then
                                if v then
                                    Set.insert option.id question.selections
                                else
                                    Set.remove option.id question.selections
                          }
        in
        ( { model | questions =
                Dict.insert question.id newQuestion model.questions }
        , Cmd.none )

    TransferFieldInput s ->
        ( { model | transfer_to = s }, Cmd.none )

    TransferInvite v ->
        ( { model | loading = model.loading + 1 }
        , postTransferInvite v model )

    GiftTicket v ->
        ( { model | loading = model.loading + 1 }
        , postGiftTicket v model )

    Posted _ ->
        ( { model | loading = model.loading - 1 }
        , Cmd.none )

    RenderButtons ->
        ( model, renderButtons () )

    NewToken s ->
        ( { model | token = s }, Cmd.none )

    TicketGifted (Ok s) ->
        ( { model | loading = model.loading - 1 }
        , Nav.load s )

    TicketGifted (Err e) ->
        ( { model | error = Just "Unable to gift ticket"
                  , loading = model.loading - 1 }
        , Cmd.none )

decodeHttpError : Http.Error -> String
decodeHttpError e =
    case e of
        Http.BadStatus s ->
            "Error from backend: " ++ String.fromInt(s)
        Http.BadBody s ->
            "Error parsing request response: " ++ s
        _ ->
            "Error making request to server! I'm probably in a bad state, try reloading."

mkTitle : String -> String
mkTitle t = "Borderland 2019 - " ++ t

viewTemplate : Model -> List (Html Msg) -> List (Html Msg)
viewTemplate model content =
    (case model.error of
        Nothing ->
            []
        Just e ->
            [ h1 [] [ text "Error!" ]
            , text e ])
    ++ [ div [] <| if model.loading > 0 then [ text <| "loading " ++ String.fromInt(model.loading) ] else [ ] ]
    ++ content

view : Model -> Browser.Document Msg
view model =
    case model.route of
        Just Home ->
            { title =
                  mkTitle "Lottery"
            , body =
                case model.registration of
                    Just r ->
                        viewTemplate model <| viewHome model.lottery r
                    Nothing ->
                        [] }

        Just RegisterPage -> { title =
                                   mkTitle "Registering"
                             , body = viewTemplate model <|
                                   [ div [] [ text "You're about to enter the wonderful world of registrering."]
                                   , a [ href "/questions/1" ] [ text "Aks me questions?" ] ] }

        Just (QuestionPage int) ->
            { title =
                  mkTitle "Questions?" -- TODO
            , body =
                viewTemplate model <| [ viewQuestionPage model.questionSets model.questions int ] }

        Nothing -> { title = mkTitle "You're lost"
                   , body = [ text "You're in a maze of websites, all alike." ] }

viewHome : Lottery -> Registration -> List (Html Msg)
viewHome l r =
    [ div []
          [ h1 [] [ text "Borderland Membership Lottery"]
          ]
    ]
    ++ [ viewRegistrationStatus l r ]
    ++ [ Maybe.withDefault (text "") <| viewVoucherStatus l r ]
    ++ viewExtraVouchers l r

viewExtraVouchers : Lottery -> Registration -> List (Html Msg)
viewExtraVouchers l r =
    case r.vouchers of
        (_::[]) ->
            []
        (_::xs) ->
            List.map (viewExtraVoucher l r) xs
        _ ->
            []

viewExtraVoucher : Lottery -> Registration -> Voucher -> Html Msg
viewExtraVoucher l r v =
    div []
        [ h2 [] [ text "You have an additional invitation "]
        , text "Send it on or gift it to a friend. "
        , text <| "It expires " ++ viewTime v.expires
        , div [] [input [ type_ "email"
                        , placeholder "Registered email"
                        , onInput (TransferFieldInput)
                        ] []
                 , input [ type_ "button"
                         , value "Transfer invite"
                         , onClick (TransferInvite v)
                         ] []
                 , input [ type_ "button"
                         , value "Gift membership"
                         , onClick (GiftTicket v)
                  ] []
                 ]
        ]

viewVoucherStatus : Lottery -> Registration -> Maybe (Html Msg)
viewVoucherStatus l r =
    case r.tickets of
        Just t ->
            Just (div [] [ h2 [] [text  "you have a ticket yay etc"]
                         , text "blah blah link to your info here" ])
        Nothing ->
            case r.vouchers of
                [] ->
                    Nothing
                (x::_) ->
                    viewPersonalVoucher l r

viewPersonalVoucher : Lottery -> Registration -> Maybe (Html Msg)
viewPersonalVoucher l r =
    head r.vouchers
        |> Maybe.andThen (\v -> Just <|
                              div [] [ h2 [] [ text "You have an invitation!" ]
                                     ,  text <| "It expires " ++ viewTime v.expires
                                     , viewPretixButton l r v.code l.ticketItem ])

viewTime : Time.Posix -> String
viewTime t =
    let
        hour = String.padLeft 2 '0' <| String.fromInt(Time.toHour Time.utc t)
        min = String.padLeft 2 '0' <| String.fromInt(Time.toMinute Time.utc t)
        sec = String.padLeft 2 '0' <| String.fromInt(Time.toSecond Time.utc t)
        day = String.fromInt(Time.toDay Time.utc t)
        mon = stringFromMonth(Time.toMonth Time.utc t)
        yr = String.fromInt(Time.toYear Time.utc t)
    in
        day ++ "-" ++ mon ++ "-" ++ yr ++ " " ++ hour ++ ":" ++ min ++ ":" ++ sec ++ " UTC"

stringFromMonth : Time.Month -> String
stringFromMonth month =
  case month of
    Time.Jan -> "Jan"
    Time.Feb -> "Feb"
    Time.Mar -> "Mar"
    Time.Apr -> "Apr"
    Time.May -> "May"
    Time.Jun -> "Jun"
    Time.Jul -> "Jul"
    Time.Aug -> "Aug"
    Time.Sep -> "Sep"
    Time.Oct -> "Oct"
    Time.Nov -> "Nov"
    Time.Dec -> "Dec"


viewPretixButton : Lottery -> Registration -> String -> String -> Html Msg
viewPretixButton l r code item =
    node "pretix-button"
        [ attribute "event" l.pretixUrl
        , attribute "items" item
        , attribute "voucher" code
        , attribute "data-email" r.email
        , on "DOMNodeInserted" (JD.succeed RenderButtons)
        ] [ text "Purchase membership" ]

viewRegistrationStatus : Lottery -> Registration -> Html Msg
viewRegistrationStatus l r =
    if r.registered then
        div [] <| [ text "You're registered!"
               ]
            ++ if l.can_register then
                   [ a [ href "/register" ] [ text "Change your answers."] ]
               else
                   []
    else
        if l.can_register then
          div []
              [ text "Click here to register for Borderland 2019: "
              , a [ href "/register" ] [ text "Register"]
              ]
        else
            div [] [ text "Alas, registration is not open :(" ]

viewQuestionPage : List QuestionSet -> Dict Int Question -> Int -> Html Msg
viewQuestionPage questionSets questions i =
    case List.drop (i-1) questionSets of
        (qset::[]) ->
            div []
                [ viewQuestionSet qset questions
                , a [ href "/"
                    , onClick (PostAnswers qset True) ]
                    [ text "Done!" ]
                ]

        (qset::_) ->
            div []
                [ viewQuestionSet qset questions
                , a [ href ("/questions/" ++ String.fromInt(i + 1))
                    , onClick (PostAnswers qset False) ]
                    [ text "Next" ]]
        [] ->
           (text "No questions like that here")

viewQuestionSet : QuestionSet -> Dict Int Question -> Html Msg
viewQuestionSet qset qs = div [] [ h1 [] [ text qset.name ]
                                 , text qset.description
                                 , viewQuestions <| questionsForSet qset qs
                                 ]
viewQuestions : List Question -> Html Msg
viewQuestions qs = div []
                        (List.map (viewQuestion) qs)

questionsForSet : QuestionSet -> Dict Int Question -> List Question
questionsForSet qset qs = Dict.filter (\key _ -> List.any (\q -> key == q.id ) qset.questions) qs |> Dict.values

viewQuestion : Question -> Html Msg
viewQuestion q =
    let
        qId = "question-" ++ (String.fromInt q.id)
    in
        div [ class "q" ]
            ([ label [ for qId ] [ text q.text ] ]
            ++ case q.type_ of
                  Number ->
                      [ input [ type_ "number"
                               , id qId
                               , value q.answer
                               , Html.Attributes.min "0"
                               , Html.Attributes.required True
                               , onInput (UpdateAnswer q.id) ] [] ]
                  Date ->
                      [ input [ type_ "date"
                               , id qId
                               , value q.answer
                               , Html.Attributes.required True
                               , onInput (UpdateAnswer q.id) ] [] ]
                  Text ->
                      [ input [ type_ "text"
                               , id qId
                               , value q.answer
                               , Html.Attributes.required True
                               , onInput (UpdateAnswer q.id) ] [] ]
                  DataList ->
                      [ input [ type_ "text"
                              , id qId
                              , value q.answer
                              , onInput (UpdateAnswer q.id)
                              , Html.Attributes.required True
                              , list <| "datalist-" ++ qId
                              ] []
                      , datalist [ id <| "datalist-" ++ qId ]
                          <| List.map (\x -> option [ value x.text ] []) q.options ]
                  MultipleChoice ->
                      (List.map (viewOption q) q.options))

viewOption : Question -> Option -> Html Msg
viewOption q o =
    let
        id_ = ("option-" ++ String.fromInt o.id)
    in
        div []
            [ input [ type_ "checkbox"
                    , id id_
                    , onCheck (ToggleCheckbox q o)
                    , checked (Set.member o.id q.selections) ] []
            , label [ for id_ ] [ text o.text ]
            ]

-- HTTP resources

getQuestions : Token -> Int -> Cmd Msg
getQuestions token i =
    authorizedGet token ("/api/questions/" ++ String.fromInt(i))
        (Http.expectJson GotQuestionSet questionSetDecoder)

postAnswers : Model -> QuestionSet -> Cmd Msg
postAnswers model qs =
    authorizedPost
                (Http.jsonBody <| Json.Encode.object
                     (List.map
                          (\q -> ((String.fromInt q.id),
                               (if Set.isEmpty q.selections then
                                    Json.Encode.string q.answer
                                else
                                    Json.Encode.list Json.Encode.string
                                    <| Set.toList
                                    <| Set.map String.fromInt q.selections)))
                          (questionsForSet qs model.questions)) )
                model.token
                ("/api/questions/" ++ String.fromInt(qs.id))
                --(Http.expectJson GotQuestionSet questionSetDecoder)
                (Http.expectWhatever Posted)

getRegistration : Token -> Cmd Msg
getRegistration token =
    authorizedGet
        token
        "/api/registration"
        (Http.expectJson GotRegistration registrationDecoder)

postRegistration : Token -> Cmd Msg
postRegistration token =
    authorizedPost Http.emptyBody token "/api/registration"
            (Http.expectJson GotRegistration registrationDecoder)

postTransferInvite : Voucher -> Model -> Cmd Msg
postTransferInvite v m
    = authorizedPost
      (Http.jsonBody (Json.Encode.object [
                           ("voucher", Json.Encode.string v.code),
                           ("email", Json.Encode.string m.transfer_to)
                          ]))
            m.token "/api/transfer" (Http.expectJson GotRegistration registrationDecoder)

postGiftTicket : Voucher -> Model -> Cmd Msg
postGiftTicket v m
    = authorizedPost
      (Http.jsonBody (Json.Encode.object [
                           ("voucher", Json.Encode.string v.code),
                           ("email", Json.Encode.string m.transfer_to)
                          ]))
          m.token "/api/gift" (Http.expectJson TicketGifted (JD.at ["url"] JD.string))

getLottery : String -> Cmd Msg
getLottery token =
    authorizedGet token "/api/lottery" (Http.expectJson GotLottery lotteryDecoder)

authorizedReq : String -> Http.Body -> Token -> String -> Http.Expect Msg -> Cmd Msg
authorizedReq method body token url expect =
    Http.request
        { url = url
        , method = method
        , headers = [ Http.header "Authorization" ("Bearer " ++ token) ]
        , body = body
        , timeout = Nothing
        , tracker = Nothing
        , expect = expect }

authorizedGet : Token -> String -> Http.Expect Msg -> Cmd Msg
authorizedGet = authorizedReq "GET" Http.emptyBody


authorizedPost : Http.Body -> Token -> String -> Http.Expect Msg -> Cmd Msg
authorizedPost = authorizedReq "POST"

-- JSON Decoders

questionSetDecoder : JD.Decoder QuestionSet
questionSetDecoder = JD.map5 QuestionSet
                      (JD.at ["description"] JD.string)
                      (JD.at ["id"] JD.int)
                      (JD.at ["priority"] JD.int)
                      (JD.at ["questions"] (JD.list
                           (JD.map6 Question
                                (JD.at ["id"] JD.int)
                                (JD.at ["question"] JD.string)
                                (JD.at ["answer"] JD.string)
                                ((JD.at ["selections"] (JD.list JD.int))
                                |> JD.andThen (\l -> JD.succeed (Set.fromList l)))
                                (JD.at ["type"] questionTypeDecoder)
                                (JD.at ["options"] (JD.list optionDecoder)))))
                      (JD.at ["name"] JD.string)

optionDecoder : JD.Decoder Option
optionDecoder = JD.map2 Option
                (JD.at ["id"] JD.int)
                (JD.at ["text"] JD.string)

questionTypeDecoder : JD.Decoder QuestionType
questionTypeDecoder = JD.string |> JD.andThen
                      (\str -> case str of
                        "text" ->
                           JD.succeed Text
                        "date" ->
                           JD.succeed Date
                        "multiple" ->
                           JD.succeed MultipleChoice
                        "datalist" ->
                           JD.succeed DataList
                        "number" ->
                           JD.succeed Number
                        e ->
                          JD.fail <| "Unknown option type " ++ e)

lotteryDecoder : JD.Decoder Lottery
lotteryDecoder = JD.map6 Lottery
                    (JD.at ["can_register"] JD.bool)
                    (JD.at ["can_transfer"] JD.bool)
                    (JD.at ["child_item"] JD.string)
                    (JD.at ["ticket_item"] JD.string)
                    (JD.at ["pretix_event_url"] JD.string)
                    (JD.at ["questions"] (JD.list JD.int))

voucherDecoder : JD.Decoder Voucher
voucherDecoder = JD.map2 Voucher
                    (JD.at ["code"] JD.string)
                    (JD.at ["expires"] Json.Decode.Extra.datetime)

ticketDecoder : JD.Decoder (Maybe Ticket)
ticketDecoder = JD.maybe <| JD.map2 Ticket
                    (JD.at ["order"] JD.string)
                    (JD.at ["url"] JD.string)

registrationDecoder : JD.Decoder Registration
registrationDecoder = JD.map4 Registration
                        (JD.at ["registered"] JD.bool)
                        (JD.at ["tickets"] ticketDecoder)
                        (JD.at ["email"] JD.string)
                        (JD.at ["vouchers"] (JD.list voucherDecoder))
