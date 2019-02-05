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
import Array
import Markdown

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
      , text : String
      , tooltip: Maybe String
      }

type alias Question
    = { id : Int
      , text : String
      , answer : String
      , selections : Set Int
      , type_ : QuestionType
      , tooltip : Maybe String
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
      , fcfsVoucher : Maybe String
      , ticketItem : String
      , pretixUrl : String
      , message: Maybe String
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
      , loading: Int
      , art : Int
      }

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
  | PostAnswers QuestionSet Bool String
  | Posted (HttpResource ())
  | ToggleCheckbox Question Option Bool
  | TransferFieldInput String
  | TransferInvite Voucher
  | GiftTicket Voucher
  | RenderButtons
  | NewToken String
  | TicketGifted (HttpResource String)
  | PostedAnswers String (HttpResource Bool)

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
            (Lottery False False Nothing "" "" Nothing [])
            Nothing
            ""
            flags
            Nothing
            2
            0
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
            ( { model | art = model.art + 1 }
            , Nav.pushUrl model.key (Url.toString url) )

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

    PostAnswers qs last next ->
        ( { model | loading = model.loading + if last then 2 else 1 }
        , Cmd.batch
            ([ postAnswers model qs next ] ++
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

    PostedAnswers next m ->
        case m of
            Ok s ->
               ( { model | loading = model.loading - 1 }
               , Nav.pushUrl model.key next )
            Err s ->
                ( { model | error = Just "Unable to send answer!"
                  , loading = model.loading - 1 }, Cmd.none )

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
mkTitle t = "Borderland 2019 Membership - " ++ t

viewTemplate : Model -> List (Html Msg) -> List (Html Msg)
viewTemplate model content =
    [ div [ id "loading"
          , class <| if (model.loading > 0) then "visible" else "hidden"
          ] []
    , div [ class "outer_container" ]
             [ div [ class "container"]
                   [ (case model.error of
                          Nothing ->
                            text ""
                          Just e ->
                            div [ class "alert alert-danger sticky-top" ]
                            [ text <| "Error! " ++ e ] )
                   , div [ class "row" ]
                         [ div [ class "col", class "col-lg-5" ]
                               <| [ div [ class "logo" ] [] ]
                               ++ content
                         , div [ class "col-6"
                               , class "col-md-7"
                               , class "artwork"
                               , class <| "art-" ++ String.fromInt((Basics.modBy 8 model.art) + 1)
                               ]
                               [ ]
                         ]
                   , div [ class "footer navbar fixed-bottom" ]
                       [ a [ class "navbar-brand"
                           , href "https://account.theborderland.se/auth/realms/master/protocol/openid-connect/logout?redirect_uri=https://memberships.theborderland.se"]
                             [ text "Log Out" ]
                       , a [ class "navbar-brand"
                           , href "mailto:memberships@theborderland.se"] [ text "Contact us" ]
                       ]
                   ]
             ]
       ]

view : Model -> Browser.Document Msg
view model =
    case model.route of
        Just Home ->
            { title =
                  mkTitle "Home"
            , body =
                case model.registration of
                    Just r ->
                        viewTemplate model <| viewHome model.lottery ++ viewRegistration model.lottery r
                    Nothing ->
                        []
            }

        Just RegisterPage -> { title =
                                   mkTitle "Registration start"
                             , body =
                                 viewTemplate model <|
                                     [ p [ class "lead" ] [ text "To get you registered we'll ask you a couple of questions." ]
                                     , p [ class "lead" ] [ text "Some of these questions are needed to make the lottery fair, others purely to satisfy our curiosity."]
                                     , p [ class "lead" ] [ text "Regardless of your answers, your chances of winning the lottery are the same." ]
                                     , a [ class "next-button"
                                         , href "/questions/1" ] [ text "Let's go!" ] ] }

        Just (QuestionPage int) ->
            { title =
                  mkTitle "Questions?"
            , body =
                viewTemplate model <| [ viewQuestionPage model.questionSets model.questions int ] }

        Nothing -> { title = mkTitle "You're lost"
                   , body = [ text "You're in a maze of websites, all alike." ] }


viewHome : Lottery ->  List (Html Msg)
viewHome lottery =
           ([ div [] [ h1 [] [ text "The Borderland 2019 Membership Lottery"]
            , (Maybe.withDefault "" lottery.message |> viewMessage) ]])

viewMessage : String -> Html Msg
viewMessage s =
     div []
         [ Markdown.toHtml [] s ]

viewRegistration : Lottery -> Registration -> List (Html Msg)
viewRegistration l r =
    case viewVoucherStatus l r of
        Just voucherStatus ->
            [ voucherStatus ]
            ++ viewExtraVouchers l r
            ++ if l.can_register then
                   [ viewRegistrationStatus l r ]
               else
                   []
        Nothing ->
            [ viewRegistrationStatus l r ]
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
        [ h2 [] [ text "You have an extra invitation."]
        , p [] [ text "You can pass it on, or gift it, to a friend. Your friend must be registered for the lottery." ]
        , p [] [ text <| "The invite expires " ++ viewTime v.expires ++ "."]
        , p [] [ text "If you select \"Transfer Invite\" your friend will get an email and they can log on here to purchase their membership. You can also select \"Gift Membership\" and pay for your friend's membership." ]
        , div [] [input [ type_ "email"
                        , placeholder "Registered email"
                        , onInput (TransferFieldInput)
                        ] []
                 , br [] []
                 , input [ type_ "button"
                         , value "Transfer Invite"
                         , onClick (TransferInvite v)
                         ] []
                 , input [ type_ "button"
                         , value "Gift Membership"
                         , onClick (GiftTicket v)
                  ] []
                 ]
        ]

viewVoucherStatus : Lottery -> Registration -> Maybe (Html Msg)
viewVoucherStatus l r =
    case r.tickets of
        Just t ->
            Just (div [] [ h2 [] [ text  "You're going to The Borderland 2019!"]
                         , p [] [ text "You can view your receipt and print your entry pass "
                                , a [ href t.url ] [ text "here" ]
                                , text "." ]
                         , if l.can_transfer then
                               div [] [ p [] [ text "You're currently permitted to transfer your membership. The recipient must have registered. Please note that re-selling memberships above face value is not allowed."
                                             , div [] [ input [ type_ "email"
                                                              , placeholder "Registered email"
                                                              , onInput TransferFieldInput ] []
                                                      , input [ type_ "button"
                                                              , value "Transfer membership"
                                                              -- , onClick (Noop) TODO needs modal
                                                              ] []
                                             ]]
                                      ]
                           else
                               text ""
                         ])
        Nothing ->
            case r.vouchers of
                [] ->
                    if r.registered then
                        viewFCFSVoucher l r
                    else
                        Nothing
                (x::_) ->
                    viewPersonalVoucher l r

viewPersonalVoucher : Lottery -> Registration -> Maybe (Html Msg)
viewPersonalVoucher l r =
    head r.vouchers
        |> Maybe.andThen (\v -> Just <|
                          div [] [ h2 [] [ text "You're invited to The Borderland 2019!" ]
                                 ,  text <| "Hurry up and purchase your membership, the invitation expires " ++ viewTime v.expires ++ "!"
                                 , viewPretixButton l r v.code l.ticketItem ])

viewFCFSVoucher : Lottery -> Registration -> Maybe (Html Msg)
viewFCFSVoucher l r =
    l.fcfsVoucher |> Maybe.andThen (\v -> Just <|
        (div [] [ h2 [] [ text "First Come First Serve!" ]
                , p [] [ text "The lottery is over, but if there are memberships left over you can get them now!" ]
                , viewPretixButton l r v l.ticketItem ]))

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
        mon ++ " " ++ day ++ ". at " ++ hour ++ ":" ++ min
        -- day ++ "-" ++ mon ++ "-" ++ yr ++ " " ++ hour ++ ":" ++ min ++ ":" ++ sec ++ " UTC"

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
        ] [ text "Purchase Membership" ]

viewRegistrationStatus : Lottery -> Registration -> Html Msg
viewRegistrationStatus l r =
    if r.registered then
        div [] <| [ h2 [] [ text "You're registered!" ]
                  , p [] [ text "If you win the lottery you'll have two days to purchase your membership and to invite a friend along. Remember that your friend also has to be registered." ]
                  , p [] [ text "We'll send an e-mail when you win, but since e-mail can be unreliable we recommended you check back here once a day during the lottery period February 16th to the 22th." ]
               ]
            ++ if l.can_register then
                   [ p [] [ a [ href "/register" ]
                              [ text "If you need to, you can change your registration answers."] ]
                   ]
               else
                   []
    else
        if l.can_register then
          div [] <| [ h2 [] [ text "Registration is open!" ]
                    , p [ ]
                        [ a [ href "/register"
                            , class "lead font-weight-bold" ]
                             [ text "Click here to register for The Borderland 2019" ]
                        ]]
        else
            div [] [ p [] [ text "Hello! Registration opens here Thursday February 7th at 12:00 CET, and then you have a week to do it." ]]

viewQuestionPage : List QuestionSet -> Dict Int Question -> Int -> Html Msg
viewQuestionPage questionSets questions i =
    case List.drop (i-1) questionSets of
        (qset::[]) ->
            div []
                [ viewQuestionSet qset questions
                , a [ onClick (PostAnswers qset True "/")
                    , class "next-button"
                    , href "#"]
                    [ text "Done!" ]
                ]

        (qset::_) ->
            Html.form []
                [ viewQuestionSet qset questions
                , a [ href "#"
                    , class "next-button"
                    , onClick (PostAnswers qset False ("/questions/" ++ String.fromInt(i + 1))) ]
                         [ text "Next" ] ]
        [] ->
           (text "No questions like that here")

formatDesc : String -> List (Html Msg)
formatDesc d = -- TODO the description should be changed to Html and parsed in the decoder
    [ Markdown.toHtml [] d ]
    --String.split "\n" d |> List.map (\s -> p [ class "lead" ] [ text s ])

viewQuestionSet : QuestionSet -> Dict Int Question -> Html Msg
viewQuestionSet qset qs = div [] <| [ h1 [] [ text qset.name ] ]
                          ++ formatDesc qset.description
                          ++ [ viewQuestions <| questionsForSet qset qs ]

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
                               , placeholder <| Maybe.withDefault "" q.tooltip
                               , onInput (UpdateAnswer q.id) ] [] ]
                  Date ->
                      [ input [ type_ "date"
                               , id qId
                               , value q.answer
                               , Html.Attributes.required True
                               , placeholder <| Maybe.withDefault "" q.tooltip
                               , onInput (UpdateAnswer q.id) ] [] ]
                  Text ->
                      [ input [ type_ "text"
                               , id qId
                               , value q.answer
                               , Html.Attributes.required True
                               , onInput (UpdateAnswer q.id)
                               , placeholder <| Maybe.withDefault "" q.tooltip ]
                            [] ]
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
            [ label [ class "checkboxhack" ] [ input [ type_ "checkbox"
                                                     , id id_
                                                     , onCheck (ToggleCheckbox q o)
                                                     , checked (Set.member o.id q.selections) ] []
                                             , span [] [] ]
            , label [ for id_ ] [
                   case o.tooltip of
                       Just tooltip ->
                          div [ class "tooltipp" ]
                              [ text o.text
                              , span [ class "tooltipptext" ] [ text tooltip ]
                              ]
                       Nothing ->
                          text o.text
                  ]
            ]

-- HTTP resources

getQuestions : Token -> Int -> Cmd Msg
getQuestions token i =
    authorizedGet token ("/api/questions/" ++ String.fromInt(i))
        (Http.expectJson GotQuestionSet questionSetDecoder)

postAnswers : Model -> QuestionSet -> String -> Cmd Msg
postAnswers model qs next =
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
                (Http.expectJson (PostedAnswers next) (JD.at ["result"] JD.bool))

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
                           (JD.map7 Question
                                (JD.at ["id"] JD.int)
                                (JD.at ["question"] JD.string)
                                (JD.at ["answer"] JD.string)
                                ((JD.at ["selections"] (JD.list JD.int))
                                |> JD.andThen (\l -> JD.succeed (Set.fromList l)))
                                (JD.at ["type"] questionTypeDecoder)
                                (JD.maybe <| JD.at ["tooltip"] JD.string )
                                (JD.at ["options"] (JD.list optionDecoder)))))
                      (JD.at ["name"] JD.string)

optionDecoder : JD.Decoder Option
optionDecoder = JD.map3 Option
                (JD.at ["id"] JD.int)
                (JD.at ["text"] JD.string)
                (JD.maybe <| JD.at ["tooltip"] JD.string)

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
lotteryDecoder = JD.map7 Lottery
                    (JD.at ["can_register"] JD.bool)
                    (JD.at ["can_transfer"] JD.bool)
                    (JD.maybe <| JD.at ["fcfs_voucher"] JD.string)
                    (JD.at ["ticket_item"] JD.string)
                    (JD.at ["pretix_event_url"] JD.string)
                    (JD.maybe <| JD.at ["message"] JD.string)
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
