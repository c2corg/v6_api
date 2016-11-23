package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

object Auth {
  val feeder = csv("users.csv").random

  val header_json = Map(
    "Accept" -> "application/json",
    "Content-Type" -> "application/json; charset=UTF-8",
    "Origin" -> C2corgConf.ui_url
  )

  val header_authorization = Map(
    "Content-Type" -> "application/json",
    "Authorization" -> """JWT token="${user_token}"""",
    "Origin" -> C2corgConf.ui_url
  )

  val header_authorization_data = Map(
    "Accept" -> "application/json",
    "Authorization" -> """JWT token="${user_token}"""",
    "Content-Type" -> "application/json; charset=UTF-8",
    "Origin" -> C2corgConf.ui_url
  )

  val header_discourse_1 = Map(
    "X-CSRF-Token" -> "${forum_token}",
    "X-Requested-With" -> "XMLHttpRequest")

  val header_discourse_2 = Map(
    "Accept" -> "*/*",
    "Content-Type" -> "application/x-www-form-urlencoded; charset=UTF-8",
    "X-CSRF-Token" -> "${forum_token}",
    "X-Requested-With" -> "XMLHttpRequest")

  val header_discourse_3 = Map(
    "Content-Type" -> "application/x-www-form-urlencoded; charset=UTF-8",
    "X-CSRF-Token" -> "${forum_token}",
    "X-Requested-With" -> "XMLHttpRequest")

  val header_discourse_4 = Map(
    "Discourse-Track-View" -> "true",
    "X-CSRF-Token" -> "${forum_token}",
    "X-Requested-With" -> "XMLHttpRequest")

  val login = feed(feeder).exec(
    http("View login page")
      .get(C2corgConf.ui_url + "/auth")
      .headers(C2corgConf.header_html)
      .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password))
    .pause(5).exec(
    http("Login to API")
      .post(C2corgConf.api_url + "/users/login")
      .headers(header_json)
      .body(StringBody("""{ "username": "${username}", "password": "${password}", "remember": false, "discourse": true}""")).asJSON
      .check(
        //jsonPath("$.redirect_internal").exists.saveAs("forum_sso_redirect"),
        jsonPath("$.token").exists.saveAs("user_token")
      ))

  val loginForum = feed(feeder).exec(
    http("Forum SSO")
      .get(C2corgConf.forum_url + "/session/sso?return_path=%2F")
      .headers(C2corgConf.header_html)
      .disableFollowRedirect
      .check(
        status.is(302),
        headerRegex("Location", """sso=([^&]*)""").saveAs("sso"),
        headerRegex("Location", """sig=([^&]*)""").saveAs("sig")
      ))
    .exec(
    http("Login Form SSO")
      .get(C2corgConf.ui_url + "/auth-sso?sso=${sso}&sig=${sig}")
      .headers(C2corgConf.header_html)
      .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
    )
    .pause(5).exec(
    http("Login to API")
      .post(C2corgConf.api_url + "/users/login")
      .headers(header_json)
      .body(StringBody("""{ "username": "${username}", "password": "${password}", "remember": false, "discourse": true, "sso": "${sso}", "sig": "${sig}" }""")).asJSON
      .check(
        jsonPath("$.redirect").exists.saveAs("redirect"),
        jsonPath("$.token").exists.saveAs("user_token")
      ))
    .exec(
    http("SSO Login to Forum")
      .get("${redirect}")
      .headers(C2corgConf.header_html)
      .disableFollowRedirect
      .check(
        status.is(302)
      ))
    .exec(
    http("Forum Init Auth")
      .get(C2corgConf.forum_url + "/")
      .headers(C2corgConf.header_html)
      .check(
        regex("<meta name=\"csrf-token\" content=\"([^\"]+)\"").saveAs("forum_token")
      ))

}
