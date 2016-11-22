package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

object Homepage {
  val init = exec(http("View homepage")
    .get(C2corgConf.ui_url + "/")
    .headers(C2corgConf.header_html)
    .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
    .resources(
      http("Init feed")
        .get(C2corgConf.api_url + "/feed?pl=fr")
        .headers(C2corgConf.header_json)
    )
  )

  val browse = exec(http("Update feed")
    .get(C2corgConf.api_url + "/feed?pl=fr&token=246244%2C2016-11-13T08%3A27%3A02.077583")
    .headers(C2corgConf.header_json)
  )

  val initAuth = exec(http("View personal homepage")
    .get(C2corgConf.ui_url + "/")
    .headers(C2corgConf.header_html)
    .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
    .resources(
      http("Init personal feed")
        .get(C2corgConf.api_url + "/personal-feed?pl=fr")
        .headers(Auth.header_authorization)
    )
  )

  val browseAuth = exec(http("Update personal feed")
    .get(C2corgConf.api_url + "/personal-feed?pl=fr&token=154825%2C2016-11-15T14%3A41%3A09.563211")
    .headers(Auth.header_authorization)
  )
}
