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

  val login = feed(feeder).exec(
    http("View login page")
      .get(C2corgConf.ui_url + "/auth")
      .headers(C2corgConf.header_html)
      .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
    )
  .pause(5)
  .exec(
    http("Login to API")
      .post(C2corgConf.api_url + "/users/login")
      .headers(header_json)
      .body(StringBody("""{ "username": "${username}", "password": "${password}", "remember": false, "discourse": true}""")).asJSON
      .check(
        //jsonPath("$.redirect_internal").exists.saveAs("forum_sso_redirect"),
        jsonPath("$.token").exists.saveAs("user_token")
      )
  )
}
