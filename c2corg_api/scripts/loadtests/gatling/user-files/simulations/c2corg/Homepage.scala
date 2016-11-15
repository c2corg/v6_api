package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._
import io.gatling.jdbc.Predef._

object Homepage {
  val init = exec(http("View homepage")
    .get("/")
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
}
